#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
from rakshak.engine import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Raksha Privacy Firewall")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        run_pipeline(Path(args.input), Path(args.output))
        return 0
    except Exception as exc:
        # Never print input content, identifiers, or secrets.
        print(f"Raksha failed safely: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())