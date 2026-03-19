# JSON Message Transformer

Python scripts for validating JSON, cleaning malformed JSON, and converting email-style JSON exports into CSV.

The main use case is a JSON export where each record represents an email-style message and includes fields such as:

- `Id`
- `CreatedDate`
- `Subject`
- `TextBody`
- `Headers`

The converter can:

- remove duplicate source records
- split long threaded message bodies into separate message rows
- keep related messages grouped with a shared `thread_id`
- extract `from`, `to`, `sent_at`, `subject`, and `message_body`
- generate unique `message_id` values for each output row

## Requirements

- Python 3.9 or newer
- No external dependencies

## Files

- `json_to_csv.py`: main converter
- `fix_json.py`: removes invisible characters from malformed JSON
- `validate_json.py`: validates JSON and shows basic structure info
- `sample_data.json`: small email-style sample input

## Quick Start

Run the converter on your own JSON file:

```bash
python3 json_to_csv.py /path/to/your-file.json -o /path/to/output.csv
```

If your JSON contains full email threads inside `TextBody` and you want one CSV row per extracted message:

```bash
python3 json_to_csv.py /path/to/your-file.json --split-thread -o /path/to/output.csv
```

## Typical Workflow

### 1. Validate the JSON

```bash
python3 validate_json.py /path/to/your-file.json
```

### 2. Fix the JSON if needed

If the file contains invisible characters or leading/trailing junk:

```bash
python3 fix_json.py /path/to/your-file.json
```

This creates a new file ending in `_fixed.json` unless you use `--overwrite`.

### 3. Convert to CSV

Without thread splitting:

```bash
python3 json_to_csv.py /path/to/your-file.json -o /path/to/output.csv
```

With thread splitting:

```bash
python3 json_to_csv.py /path/to/your-file.json --split-thread -o /path/to/output.csv
```

## What `--split-thread` Does

When `--split-thread` is used, the converter tries to break a rendered email thread into separate message rows.

It detects common thread markers such as:

- `From:`
- `Sent:`
- `To:`
- `Subject:`
- `Original Message`
- `On ... wrote:`

It also includes support for common Latin-language header variants such as:

- French: `De`, `Envoyé`, `À`, `Objet`
- Italian: `Da`, `Inviato`, `Oggetto`
- Spanish: `De`, `Enviado`, `Para`, `Asunto`
- Portuguese: `De`, `Enviado`, `Para`, `Assunto`

This parsing is heuristic because rendered thread text is not a true raw-email format.

## Output Columns For Email Datasets

The CSV output for email-style datasets includes:

- `message_id`
- `sent_at`
- `from`
- `message_body`
- `subject`
- `to`
- `thread_id`

## Duplicate Handling

The converter removes duplicates in two stages:

1. Source-level duplicate removal
   Records with the same message content are removed before splitting.

2. Split-message duplicate removal
   If thread splitting produces repeated message rows with the same meaning, those duplicates are removed as well.

## Thread and Message IDs

- `thread_id` stays consistent across all extracted messages that came from the same original thread.
- `message_id` is generated from `from` and `to`, with a numeric suffix added when needed to keep each output row unique.

## CSV Output Behavior

- All CSV fields are written with double quotes.
- The output is UTF-8 encoded.
- If the generated CSV would exceed 128 MiB, the converter automatically splits it into multiple files.

For example, if you request:

```bash
python3 json_to_csv.py input.json --split-thread -o output.csv
```

The script may produce:

- `output.csv`
- `output_part2.csv`
- `output_part3.csv`

Each file includes the same header row and continues the data from the previous file.

## Basic Examples

Convert a file in the current folder:

```bash
python3 json_to_csv.py input.json -o output.csv
```

Split message threads into multiple rows:

```bash
python3 json_to_csv.py input.json --split-thread -o output.csv
```

Validate and then convert:

```bash
python3 validate_json.py input.json
python3 json_to_csv.py input.json --split-thread -o output.csv
```

Clean, then convert the cleaned file:

```bash
python3 fix_json.py input.json
python3 json_to_csv.py input_fixed.json --split-thread -o output.csv
```

## Example With Included Sample File

The included `sample_data.json` is fake data, but it follows the same email-message structure the converter is designed for.

```bash
python3 json_to_csv.py sample_data.json -o sample_output.csv
```

To test thread splitting with the sample file:

```bash
python3 json_to_csv.py sample_data.json --split-thread -o sample_output.csv
```

## Notes And Limitations

- The cleanest results come from source exports where each row is already one message.
- Thread splitting works best when email headers are preserved in the body text.
- If the source contains rendered reply chains, some parsing is approximate.
- The script uses only the Python standard library, which makes it easy to share with customers.
