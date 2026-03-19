#!/usr/bin/env python3
"""
JSON to CSV Converter
Converts JSON files to CSV format, handling nested and complex structures.
"""

import json
import csv
import sys
import argparse
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
from collections import OrderedDict


THREAD_SPLIT_MARKERS = (
    "--------------- Original Message ---------------",
    "-----Original Message-----",
    "Message d'origine",
    "Messaggio originale",
    "Mensaje original",
    "Mensagem original",
)
MAX_MESSAGE_BODY_LENGTH = 65536
HEADER_ALIASES = {
    "from": "from",
    "de": "from",
    "da": "from",
    "sent": "sent",
    "envoye": "sent",
    "envoyé": "sent",
    "inviato": "sent",
    "enviado": "sent",
    "to": "to",
    "a": "to",
    "à": "to",
    "para": "to",
    "cc": "cc",
    "subject": "subject",
    "objet": "subject",
    "oggetto": "subject",
    "asunto": "subject",
    "assunto": "subject",
}
BOUNDARY_HEADER_KEYS = {"from"}
REPLY_INTRO_PATTERNS = (
    r"^On (.+?) wrote:\s*$",
    r"^Le (.+?) a écrit\s*:\s*$",
    r"^Il giorno (.+?) ha scritto\s*:\s*$",
    r"^El (.+?) escribió\s*:\s*$",
    r"^Em (.+?) escreveu\s*:\s*$",
)


def flatten_dict(data: Dict[str, Any], parent_key: str = '', sep: str = '_') -> Dict[str, Any]:
    """
    Flatten nested dictionaries into a single-level dictionary.
    
    Args:
        data: Dictionary to flatten
        parent_key: Parent key for nested items
        sep: Separator between nested keys
        
    Returns:
        Flattened dictionary
    """
    items = []
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        
        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, sep=sep).items())
        elif isinstance(value, list):
            # Convert list to string representation
            items.append((new_key, json.dumps(value)))
        else:
            items.append((new_key, value))
    
    return dict(items)


def find_all_objects_in_arrays(data: Any, objects: List = None) -> List:
    """
    Recursively find all objects (dicts) that are inside arrays in a nested JSON structure.
    Collects all dict objects from all arrays found.
    
    Args:
        data: Data to search
        objects: List to accumulate objects
        
    Returns:
        List of all dict objects found in arrays
    """
    if objects is None:
        objects = []
    
    if isinstance(data, list):
        # Collect all dict objects from this array
        for item in data:
            if isinstance(item, dict):
                objects.append(item)
            else:
                # Recursively search inside non-dict items
                find_all_objects_in_arrays(item, objects)
    elif isinstance(data, dict):
        for value in data.values():
            find_all_objects_in_arrays(value, objects)
    
    return objects


def is_email_message_dataset(rows: List[Any]) -> bool:
    """Detect Salesforce-style EmailMessage exports."""
    if not rows or not all(isinstance(row, dict) for row in rows):
        return False

    required_keys = {"Id", "CreatedDate", "Subject", "TextBody"}
    return all(required_keys.issubset(row.keys()) for row in rows)


def extract_first_match(patterns: List[str], text: str) -> str:
    """Return the first captured regex match found in the text."""
    if not text:
        return ""

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()

    return ""


def extract_thread_id(subject: str, text_body: str, headers: str) -> str:
    """Extract the most stable thread identifier available."""
    return extract_first_match(
        [
            r"\[\s*ref:([^\]]+)\]",
            r"ref:([^\s]+)",
            r"thread::([^:]+)::",
            r"^In-Reply-To:\s*<([^>]+)>$",
            r"^References:\s*.*<([^>]+)>\s*$",
        ],
        "\n".join([subject, text_body, headers]),
    )


def sanitize_message_part(value: str) -> str:
    """Normalize address-like values into a compact ID-safe token."""
    cleaned = re.sub(r"<mailto:.*?>", "", value or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"https?://\S+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^\w@.+-]+", "_", cleaned.strip().lower())
    return cleaned.strip("_")


def dedupe_email_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Remove duplicate email records before any message splitting happens."""
    deduped_rows = []
    seen = set()

    for row in rows:
        if not isinstance(row, dict):
            deduped_rows.append(row)
            continue

        signature_parts = [
            str(row.get("CreatedDate", "") or ""),
            str(row.get("Subject", "") or ""),
            str(row.get("TextBody", "") or ""),
            str(row.get("Headers", "") or ""),
        ]
        signature = hashlib.sha256("\x1f".join(signature_parts).encode("utf-8")).hexdigest()
        if signature in seen:
            continue
        seen.add(signature)
        deduped_rows.append(row)

    return deduped_rows, len(rows) - len(deduped_rows)


def assign_unique_message_ids(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create unique message IDs from to/from values, with suffixes as needed."""
    counters = {}

    for row in rows:
        from_part = sanitize_message_part(str(row.get("from", "") or ""))
        to_part = sanitize_message_part(str(row.get("to", "") or ""))
        base_parts = [part for part in (from_part, to_part) if part]
        base_id = "__".join(base_parts) if base_parts else sanitize_message_part(str(row.get("thread_id", "") or "")) or "message"

        count = counters.get(base_id, 0) + 1
        counters[base_id] = count
        row["message_id"] = base_id if count == 1 else f"{base_id}_{count}"

    return rows


def normalize_message_body_for_dedupe(text: str) -> str:
    """Normalize message body text for duplicate detection."""
    text = normalize_whitespace(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def normalize_sent_at_for_dedupe(value: str) -> str:
    """Normalize timestamps to minute precision for duplicate detection."""
    value = (value or "").strip()
    if not value:
        return ""

    formats = (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%A, %B %d, %Y %I:%M %p",
        "%m/%d/%Y, %I:%M %p",
        "%d/%m/%Y, %H:%M",
    )

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            continue

    return value


def dedupe_split_message_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Remove duplicate split messages that carry the same meaning/content."""
    deduped_rows = []
    seen = set()

    for row in rows:
        signature_parts = [
            str(row.get("thread_id", "") or "").strip().lower(),
            normalize_sent_at_for_dedupe(str(row.get("sent_at", "") or "")),
            sanitize_message_part(str(row.get("from", "") or "")),
            sanitize_message_part(str(row.get("to", "") or "")),
            normalize_whitespace(str(row.get("subject", "") or "")).lower(),
            normalize_message_body_for_dedupe(str(row.get("message_body", "") or "")),
        ]
        signature = hashlib.sha256("\x1f".join(signature_parts).encode("utf-8")).hexdigest()
        if signature in seen:
            continue
        seen.add(signature)
        deduped_rows.append(row)

    return deduped_rows, len(rows) - len(deduped_rows)


def normalize_whitespace(text: str) -> str:
    """Trim surrounding whitespace while preserving interior line breaks."""
    return re.sub(r"\n{3,}", "\n\n", text.strip())


def strip_quote_prefix(line: str) -> str:
    """Remove common quote prefixes from forwarded/replied email text."""
    return re.sub(r"^\s*(>\s*)+", "", line).strip()


def normalize_header_line(line: str) -> str:
    """Normalize quoted/markdown-style header lines like '> *From:* Bob'."""
    normalized = strip_quote_prefix(line)
    normalized = re.sub(
        r"^\*(From|De|Da|Sent|Envoyé|Envoye|Inviato|Enviado|To|A|À|Para|Cc|Subject|Objet|Oggetto|Asunto|Assunto):\*\s*",
        r"\1: ",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized.strip()


def get_reply_intro_info(lines: List[str], idx: int) -> Tuple[int, str]:
    """Return the span and timestamp-like text used by a wrapped reply marker."""
    parts = []
    for pos in range(idx, min(idx + 3, len(lines))):
        parts.append(normalize_header_line(lines[pos]))
        candidate = re.sub(r"\s+", " ", " ".join(parts)).strip()
        for pattern in REPLY_INTRO_PATTERNS:
            match = re.match(pattern, candidate, re.IGNORECASE)
            if match:
                return pos - idx + 1, match.group(1).strip()
    return 0, ""


def split_thread_segments(text_body: str) -> List[str]:
    """Split a rendered email thread into individual message chunks."""
    lines = text_body.splitlines()
    if not lines:
        return []

    boundary_indices = []
    for idx, line in enumerate(lines):
        stripped = normalize_header_line(line)
        if stripped in THREAD_SPLIT_MARKERS:
            if idx + 1 < len(lines):
                boundary_indices.append(idx + 1)
            continue
        header_match = match_header_line(stripped)
        if idx > 0 and header_match and canonical_header_key(header_match.group(1)) in BOUNDARY_HEADER_KEYS:
            boundary_indices.append(idx)
            continue
        span, _ = get_reply_intro_info(lines, idx)
        if idx > 0 and span:
            boundary_indices.append(idx)

    if not boundary_indices:
        return [normalize_whitespace(text_body)] if text_body.strip() else []

    starts = sorted(set([0] + boundary_indices))
    segments = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(lines)
        chunk = "\n".join(lines[start:end]).strip()
        if chunk:
            segments.append(chunk)

    return segments


def trim_thread_to_limit(text_body: str, max_length: int = MAX_MESSAGE_BODY_LENGTH) -> str:
    """
    Keep the newest content and drop oldest reply segments from the bottom
    until the body fits within the requested length.
    """
    normalized_body = text_body.strip()
    if len(normalized_body) <= max_length:
        return normalized_body

    segments = split_thread_segments(normalized_body)
    if not segments:
        return normalized_body[:max_length].rstrip()

    kept_segments = list(segments)
    while len("\n\n".join(kept_segments)) > max_length and len(kept_segments) > 1:
        kept_segments.pop()

    trimmed_body = "\n\n".join(kept_segments).strip()
    if len(trimmed_body) <= max_length:
        return trimmed_body

    return trimmed_body[:max_length].rstrip()


def parse_segment_metadata(segment: str) -> Tuple[Dict[str, str], str]:
    """Parse inline email headers from a split thread segment."""
    lines = segment.splitlines()
    while lines and normalize_header_line(lines[0]) in THREAD_SPLIT_MARKERS:
        lines.pop(0)

    metadata = {"from": "", "sent_at": "", "subject": "", "to": ""}
    body_start = 0
    last_header_key = ""

    for idx, line in enumerate(lines):
        stripped = normalize_header_line(line)
        if not stripped:
            body_start = idx + 1
            break

        match = match_header_line(stripped)
        if match:
            key = canonical_header_key(match.group(1))
            value = match.group(2).strip()
            if key == "sent":
                metadata["sent_at"] = value
            elif key == "from":
                metadata["from"] = value
            elif key == "subject":
                metadata["subject"] = value
            elif key == "to":
                metadata["to"] = value
            last_header_key = key
            body_start = idx + 1
            continue

        on_wrote_span, on_wrote_sent_at = get_reply_intro_info(lines, idx) if idx == 0 else (0, "")
        if on_wrote_span:
            metadata["sent_at"] = metadata["sent_at"] or on_wrote_sent_at
            body_start = idx + on_wrote_span
            continue

        if last_header_key in {"from", "to", "cc", "subject"} and line.startswith((" ", "\t", ">")):
            continuation = strip_quote_prefix(line)
            if continuation:
                if last_header_key == "from":
                    metadata["from"] = f"{metadata['from']} {continuation}".strip()
                elif last_header_key == "to":
                    metadata["to"] = f"{metadata['to']} {continuation}".strip()
                elif last_header_key == "subject":
                    metadata["subject"] = f"{metadata['subject']} {continuation}".strip()
                body_start = idx + 1
                continue

        break

    body_lines = []
    for line in lines[body_start:]:
        cleaned = strip_quote_prefix(line)
        if cleaned == ">":
            cleaned = ""
        body_lines.append(cleaned)
    body = normalize_whitespace("\n".join(body_lines))
    return metadata, body


def canonical_header_key(raw_key: str) -> str:
    """Map localized header labels to canonical field names."""
    return HEADER_ALIASES.get(raw_key.strip().lower(), raw_key.strip().lower())


def match_header_line(line: str):
    """Match localized email header lines."""
    return re.match(
        r"^(From|De|Da|Sent|Envoyé|Envoye|Inviato|Enviado|To|A|À|Para|Cc|Subject|Objet|Oggetto|Asunto|Assunto):\s*(.+)$",
        line,
        re.IGNORECASE,
    )


def transform_email_message_row(row: Dict[str, Any], split_thread: bool = False) -> List[Dict[str, Any]]:
    """Map EmailMessage rows into compact CSV-friendly rows."""
    subject = str(row.get("Subject", "") or "")
    text_body = str(row.get("TextBody", "") or "").strip()
    headers = str(row.get("Headers", "") or "")
    base_message_id = str(row.get("Id", "") or "")

    to_value = extract_first_match(
        [
            r"^To:\s*(.+)$",
        ],
        text_body,
    )
    from_value = extract_first_match(
        [
            r"^From:\s*(.+)$",
            r"^De:\s*(.+)$",
            r"^Da:\s*(.+)$",
        ],
        text_body,
    )

    thread_id = extract_thread_id(subject, text_body, headers) or base_message_id

    if not split_thread:
        trimmed_body = trim_thread_to_limit(text_body)
        return [{
            "message_id": base_message_id,
            "sent_at": row.get("CreatedDate", ""),
            "from": from_value,
            "message_body": trimmed_body,
            "subject": subject,
            "to": to_value,
            "thread_id": thread_id,
        }]

    segments = split_thread_segments(text_body)
    if not segments:
        segments = [text_body]

    transformed_rows = []
    last_known_sent_at = str(row.get("CreatedDate", "") or "")
    for index, segment in enumerate(segments):
        metadata, body = parse_segment_metadata(segment)
        final_body = body if body else normalize_whitespace(segment)
        if not final_body or re.fullmatch(r"[>\s]*", final_body):
            continue
        sent_at = row.get("CreatedDate", "") if index == 0 else (metadata["sent_at"] or last_known_sent_at)
        if sent_at:
            last_known_sent_at = sent_at
        transformed_rows.append({
            "message_id": base_message_id if index == 0 else f"{base_message_id}#{index}",
            "sent_at": sent_at,
            "from": from_value if index == 0 else metadata["from"],
            "message_body": final_body,
            "subject": subject if index == 0 else (metadata["subject"] or subject),
            "to": to_value if index == 0 else metadata["to"],
            "thread_id": thread_id,
        })

    return transformed_rows


def json_to_csv(
    input_file: str,
    output_file: str = None,
    flatten: bool = True,
    split_thread: bool = False,
) -> str:
    """
    Convert JSON file to CSV file.
    
    Args:
        input_file: Path to input JSON file
        output_file: Path to output CSV file (optional, defaults to input_file.csv)
        flatten: Whether to flatten nested JSON structures
        split_thread: Whether to split email threads into multiple message rows
        
    Returns:
        Path to the output CSV file
    """
    # Resolve file paths
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    if output_file is None:
        output_path = input_path.with_suffix('.csv')
    else:
        output_path = Path(output_file)
    
    # Read JSON file
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON file: {e}")
    
    # Handle different JSON structures
    if isinstance(json_data, list):
        rows = json_data
    elif isinstance(json_data, dict):
        # First, try to find all dict objects inside any arrays
        objects = find_all_objects_in_arrays(json_data)
        
        if objects:
            rows = objects
        else:
            # If no objects in arrays found, check top-level keys
            list_keys = [k for k, v in json_data.items() if isinstance(v, list)]
            if list_keys:
                rows = json_data[list_keys[0]]
            else:
                rows = [json_data]
    else:
        raise ValueError("JSON must be an object or array of objects")
    
    if not rows:
        raise ValueError("No data found in JSON file")

    email_dataset = is_email_message_dataset(rows)

    if email_dataset:
        rows, removed_duplicates = dedupe_email_rows(rows)
        transformed_rows = []
        for row in rows:
            transformed_rows.extend(transform_email_message_row(row, split_thread=split_thread))
        transformed_rows, removed_split_duplicates = dedupe_split_message_rows(transformed_rows)
        rows = assign_unique_message_ids(transformed_rows)
        flatten = False
    else:
        removed_duplicates = 0
        removed_split_duplicates = 0

    # Flatten nested structures if requested
    if flatten:
        rows = [flatten_dict(row) if isinstance(row, dict) else row for row in rows]
    
    # Extract all unique column names
    fieldnames = OrderedDict()
    for row in rows:
        if isinstance(row, dict):
            for key in row.keys():
                fieldnames[key] = None
    
    if not fieldnames:
        raise ValueError("No dictionary rows found in JSON")
    
    # Write to CSV
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(
                f,
                fieldnames=fieldnames.keys(),
                quoting=csv.QUOTE_ALL,
            )
            writer.writeheader()
            for row in rows:
                if isinstance(row, dict):
                    writer.writerow(row)
        
        print(f"✓ Successfully converted JSON to CSV")
        print(f"  Input:  {input_path}")
        print(f"  Output: {output_path}")
        if email_dataset:
            print(f"  Source duplicates removed: {removed_duplicates}")
            print(f"  Split-message duplicates removed: {removed_split_duplicates}")
        print(f"  Rows:   {len(rows)}")
        print(f"  Columns: {len(fieldnames)}")
        
        return str(output_path)
    
    except IOError as e:
        raise IOError(f"Failed to write CSV file: {e}")


def main():
    """Command-line interface for JSON to CSV converter."""
    parser = argparse.ArgumentParser(
        description='Convert JSON files to CSV format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python json_to_csv.py data.json
  python json_to_csv.py data.json -o output.csv
  python json_to_csv.py data.json --no-flatten
  python json_to_csv.py 10_records.json --split-thread
        """
    )
    
    parser.add_argument('input_file', help='Path to input JSON file')
    parser.add_argument('-o', '--output', dest='output_file', 
                       help='Path to output CSV file (default: input_file.csv)')
    parser.add_argument('--no-flatten', dest='flatten', action='store_false',
                       default=True, help='Do not flatten nested JSON structures')
    parser.add_argument('--split-thread', action='store_true',
                       help='Split EmailMessage thread bodies into separate CSV rows')
    
    args = parser.parse_args()
    
    try:
        json_to_csv(args.input_file, args.output_file, args.flatten, args.split_thread)
    except (FileNotFoundError, ValueError, IOError) as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"✗ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
