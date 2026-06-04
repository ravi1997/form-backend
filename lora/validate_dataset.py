#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def validate_record(record, line_no):
    required = {"instruction", "response"}
    missing = sorted(required - set(record))
    if missing:
        raise ValueError(f"line {line_no}: missing required fields: {', '.join(missing)}")

    if not isinstance(record["instruction"], str) or not record["instruction"].strip():
        raise ValueError(f"line {line_no}: instruction must be a non-empty string")
    if not isinstance(record["response"], str) or not record["response"].strip():
        raise ValueError(f"line {line_no}: response must be a non-empty string")

    if "system" in record and not isinstance(record["system"], str):
        raise ValueError(f"line {line_no}: system must be a string")
    if "tags" in record and (
        not isinstance(record["tags"], list) or not all(isinstance(tag, str) for tag in record["tags"])
    ):
        raise ValueError(f"line {line_no}: tags must be an array of strings")
    if "mode" in record and record["mode"] not in {"reasoning", "coding", "json", "summarization", "general"}:
        raise ValueError(f"line {line_no}: invalid mode value")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("lora/data/train.jsonl")
    if not path.exists():
        print(f"missing dataset: {path}", file=sys.stderr)
        return 1

    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            record = json.loads(raw)
            if not isinstance(record, dict):
                raise ValueError(f"line {line_no}: record must be a JSON object")
            validate_record(record, line_no)
            count += 1

    print(f"ok: {count} records validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

