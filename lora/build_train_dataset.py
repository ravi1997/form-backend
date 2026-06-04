#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_SOURCES = [
    "lora/data/train.example.jsonl",
    "lora/data/generated.ridp.jsonl",
    "lora/data/generated.openapi.jsonl",
]

DEFAULT_MODE_LIMITS = {
    "json": 300,
    "coding": 300,
    "reasoning": 300,
    "summarization": 300,
    "general": 300,
}


def key_for(record: dict) -> str:
    payload = {
        "instruction": record.get("instruction", "").strip(),
        "response": record.get("response", "").strip(),
        "mode": record.get("mode", "general"),
        "system": record.get("system", "").strip() if isinstance(record.get("system"), str) else "",
        "tags": tuple(record.get("tags", []) or []),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def load_records(paths: list[Path]) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if isinstance(rec, dict):
                rec["_source"] = path.name
                records.append(rec)
    return records


def balance_records(records: list[dict], limits: dict[str, int]) -> list[dict]:
    by_mode: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        mode = rec.get("mode", "general")
        by_mode[mode].append(rec)

    balanced: list[dict] = []
    for mode in ["json", "coding", "reasoning", "summarization", "general"]:
        limit = limits.get(mode, 0)
        balanced.extend(by_mode.get(mode, [])[:limit])

    return balanced


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge and balance LoRA training datasets.")
    parser.add_argument("--output", default="lora/data/train.jsonl")
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--limit-json", type=int, default=DEFAULT_MODE_LIMITS["json"])
    parser.add_argument("--limit-coding", type=int, default=DEFAULT_MODE_LIMITS["coding"])
    parser.add_argument("--limit-reasoning", type=int, default=DEFAULT_MODE_LIMITS["reasoning"])
    parser.add_argument("--limit-summarization", type=int, default=DEFAULT_MODE_LIMITS["summarization"])
    parser.add_argument("--limit-general", type=int, default=DEFAULT_MODE_LIMITS["general"])
    args = parser.parse_args()

    sources = [Path(p) for p in (args.source or DEFAULT_SOURCES)]
    records = load_records(sources)

    seen: set[str] = set()
    deduped: list[dict] = []
    for rec in records:
        k = key_for(rec)
        if k in seen:
            continue
        seen.add(k)
        rec.pop("_source", None)
        deduped.append(rec)

    balanced = balance_records(
        deduped,
        {
            "json": args.limit_json,
            "coding": args.limit_coding,
            "reasoning": args.limit_reasoning,
            "summarization": args.limit_summarization,
            "general": args.limit_general,
        },
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        for rec in balanced:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    counts = Counter(rec.get("mode", "general") for rec in balanced)
    print(f"wrote {len(balanced)} records to {output}")
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
