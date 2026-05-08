"""
Template for WAT framework tools.
Copy this file, rename it, and implement the core logic below.
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def run(input_value: str) -> dict:
    """
    Core logic for this tool. Replace with actual implementation.
    Returns a dict that gets printed as JSON to stdout.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set in .env")

    # --- Replace below with real logic ---
    result = {
        "status": "ok",
        "input": input_value,
        "output": f"Processed: {input_value}",
    }
    # --- End of logic ---

    return result


def main():
    parser = argparse.ArgumentParser(description="WAT tool template")
    parser.add_argument("--input", required=True, help="The input value to process")
    parser.add_argument("--output-file", help="Optional path to write JSON output")
    args = parser.parse_args()

    try:
        result = run(args.input)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)

    output = json.dumps(result, indent=2)
    print(output)

    if args.output_file:
        os.makedirs(os.path.dirname(args.output_file) or ".", exist_ok=True)
        with open(args.output_file, "w") as f:
            f.write(output)


if __name__ == "__main__":
    main()
