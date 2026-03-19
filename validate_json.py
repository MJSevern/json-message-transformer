#!/usr/bin/env python3
"""
JSON Validator Script
Validates JSON files and provides detailed error information.
"""

import json
import sys
import os
from pathlib import Path


def validate_json_file(file_path):
    """
    Validate a JSON file and return detailed information.

    Args:
        file_path (str): Path to the JSON file to validate

    Returns:
        tuple: (is_valid, message, json_data)
    """
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}", None

        # Check if file is readable
        if not os.access(file_path, os.R_OK):
            return False, f"File not readable: {file_path}", None

        # Try to parse JSON
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        # If successful, provide some basic info
        if isinstance(json_data, dict):
            num_keys = len(json_data)
            info = f"Valid JSON object with {num_keys} top-level keys"
        elif isinstance(json_data, list):
            num_items = len(json_data)
            info = f"Valid JSON array with {num_items} items"
        else:
            info = f"Valid JSON (type: {type(json_data).__name__})"

        return True, info, json_data

    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON: {e.msg} at line {e.lineno}, column {e.colno}"
        return False, error_msg, None

    except UnicodeDecodeError as e:
        error_msg = f"Encoding error: {e}. File may contain invalid UTF-8 characters."
        return False, error_msg, None

    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        return False, error_msg, None


def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) != 2:
        print("Usage: python validate_json.py <json_file>")
        print("Example: python validate_json.py data.json")
        sys.exit(1)

    file_path = sys.argv[1]

    print(f"Validating JSON file: {file_path}")
    print("-" * 50)

    is_valid, message, json_data = validate_json_file(file_path)

    if is_valid:
        print("✅ VALID JSON")
        print(f"📄 {message}")

        # Show a preview of the structure
        if isinstance(json_data, dict):
            print("\n📋 Top-level keys:")
            for i, key in enumerate(list(json_data.keys())[:10]):  # Show first 10 keys
                print(f"   {i+1}. {key}")
            if len(json_data) > 10:
                print(f"   ... and {len(json_data) - 10} more keys")
        elif isinstance(json_data, list) and json_data:
            print(f"\n📋 First item structure:")
            if isinstance(json_data[0], dict):
                print(f"   Array of objects with keys: {list(json_data[0].keys())}")
            else:
                print(f"   Array of {type(json_data[0]).__name__}s")

    else:
        print("❌ INVALID JSON")
        print(f"🚨 {message}")

    print("-" * 50)
    return 0 if is_valid else 1


if __name__ == "__main__":
    sys.exit(main())