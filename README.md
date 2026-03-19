# JSON Message Transformer

Python scripts for validating JSON, cleaning malformed JSON, and transforming email-style JSON exports into CSV.

## Files

- `json_to_csv.py`: main transformer
- `fix_json.py`: strips invisible characters and rewrites a JSON file
- `validate_json.py`: validates JSON and shows basic structure info
- `sample_data.json`: small sample input

## Requirements

- Python 3.9+
- No external dependencies

## Main Use Case

The main transformer supports email-style JSON exports where each record contains fields like:

- `Id`
- `CreatedDate`
- `Subject`
- `TextBody`
- `Headers`

For those datasets, the script can:

- remove duplicate source records
- split threaded email bodies into separate message rows
- extract `from`, `to`, `sent_at`, `subject`, and `thread_id`
- generate unique `message_id` values

## Usage

Validate a JSON file:

```bash
python3 validate_json.py input.json
```

Clean a JSON file before processing:

```bash
python3 fix_json.py input.json
```

Convert JSON to CSV without thread splitting:

```bash
python3 json_to_csv.py input.json -o output.csv
```

Convert JSON to CSV and split threaded message bodies:

```bash
python3 json_to_csv.py input.json --split-thread -o output.csv
```

## Output Columns For Email Datasets

- `message_id`
- `sent_at`
- `from`
- `message_body`
- `subject`
- `to`
- `thread_id`

## Notes

- `thread_id` is preserved across messages split from the same source record.
- `message_id` is built from `from` and `to`, with a numeric suffix added when needed.
- Duplicate removal happens both before splitting and after splitting.
- Split-thread parsing is heuristic because rendered email threads are not raw message objects.

## Example

```bash
python3 json_to_csv.py sample_data.json -o sample_output.csv
```
