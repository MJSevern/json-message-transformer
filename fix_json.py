# README
# 
# How to use it: You can run it from your terminal like this:
# This will create a new file called '10_records_fixed.json' safely without overwriting
# python3 fix_json.py 10_records.json
# If you want the script to overwrite the file you pass in directly instead of creating a copy, 
# you can use the -o or --overwrite flag:
# python3 fix_json.py -o 10_records.json
#
#
import argparse
import json
import sys
import os

def fix_json_file(filepath, overwrite=False):
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' does not exist.")
        sys.exit(1)
        
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)
        
    # Strip invisible Unicode characters and whitespace from the beginning and end
    # \u200b = Zero-width space
    # \ufeff = Byte Order Mark (BOM)
    # \u200e = Left-to-Right Mark
    # \u200f = Right-to-Left Mark
    invisible_chars = '\u200b\ufeff\u200e\u200f \n\r\t'
    cleaned_data = data.strip(invisible_chars)
    
    # Verify if it's valid JSON now
    try:
        json.loads(cleaned_data)
        print("Success: The cleaned data is valid JSON.")
    except json.JSONDecodeError as e:
        print(f"Warning: The file is still not valid JSON after cleaning.\nDetails: {e}")
        print("Saving the cleaned file anyway...")

    if overwrite:
        output_filepath = filepath
    else:
        name, ext = os.path.splitext(filepath)
        output_filepath = f"{name}_fixed{ext}"

    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(cleaned_data)
        print(f"Fixed JSON successfully written to: {output_filepath}")
    except Exception as e:
        print(f"Error writing to file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix JSON files with invisible characters (like zero-width spaces).")
    parser.add_argument("filepath", help="Path to the JSON file to fix")
    parser.add_argument("-o", "--overwrite", action="store_true", help="Overwrite the original file instead of creating a new one (creates a _fixed copy by default)")
    
    args = parser.parse_args()
    fix_json_file(args.filepath, args.overwrite)
