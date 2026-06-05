#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
import ast
from pathlib import Path


MODES = ["json", "coding", "reasoning", "summarization", "general"]


def load_records(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        rec = json.loads(raw)
        if isinstance(rec, dict):
            records.append(rec)
    return records


def dump_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def make_variant(rec: dict, suffix: str, instruction_prefix: str) -> dict:
    out = dict(rec)
    out["instruction"] = f"{instruction_prefix} {normalize_text(rec.get('instruction', ''))}".strip()
    tags = list(out.get("tags", []) or [])
    if suffix not in tags:
        tags.append(suffix)
    out["tags"] = tags
    return out


def record_key(rec: dict) -> str:
    payload = {
        "instruction": normalize_text(rec.get("instruction", "")),
        "response": normalize_text(rec.get("response", "")),
        "mode": rec.get("mode", "general"),
        "system": normalize_text(rec.get("system", "")) if isinstance(rec.get("system"), str) else "",
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def synthetic_examples() -> list[dict]:
    return [
        {
            "instruction": "Return valid JSON only with keys status, task_id, and retry_after for an async job.",
            "response": json.dumps({"status": "accepted", "task_id": "abc123", "retry_after": 30}),
            "mode": "json",
            "tags": ["synthetic", "json", "async"],
        },
        {
            "instruction": "Write a Python function dedupe_preserve_order(items) that removes duplicates while preserving order. Include one assert.",
            "response": (
                "def dedupe_preserve_order(items):\n"
                "    seen = set()\n"
                "    out = []\n"
                "    for item in items:\n"
                "        if item not in seen:\n"
                "            seen.add(item)\n"
                "            out.append(item)\n"
                "    return out\n\n"
                "assert dedupe_preserve_order([1, 2, 1, 3]) == [1, 2, 3]"
            ),
            "mode": "coding",
            "tags": ["synthetic", "coding"],
        },
        {
            "instruction": "Solve this carefully: If a task takes 4 minutes and you run 3 tasks sequentially, how long does it take? Answer with the number only.",
            "response": "12",
            "mode": "reasoning",
            "tags": ["synthetic", "reasoning"],
        },
        {
            "instruction": "Summarize these invariants in 3 bullets: tenant data must be scoped by organization_id, async work returns 202 with task_id, and state changes use audit logging.",
            "response": (
                "- Tenant-owned data must include `organization_id`.\n"
                "- Async work must return `202` with a `task_id`.\n"
                "- State changes must be written through audit logging."
            ),
            "mode": "summarization",
            "tags": ["synthetic", "summarization"],
        },
        {
            "instruction": "State the default local assistant policy in one sentence.",
            "response": "Answer directly, keep outputs concise, and preserve the documented API and tenant boundaries.",
            "mode": "general",
            "tags": ["synthetic", "general"],
        },
    ]


def load_repo_mined_examples(root: Path) -> list[dict]:
    examples: list[dict] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "lora/data" in path.as_posix():
            continue
        if path.suffix not in {".py", ".md", ".txt", ".yaml", ".yml", ".json"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        rel = path.relative_to(root).as_posix()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if path.suffix in {".md", ".txt"}:
            headings = [line.lstrip("#").strip() for line in lines if line.startswith("#")]
            if headings:
                examples.append(
                    {
                        "instruction": f"Summarize the main topics in {rel}.",
                        "response": "\n".join(f"- {h}" for h in headings[:5]),
                        "mode": "summarization",
                        "tags": ["repo", "docs", "unique"],
                    }
                )
            if "organization_id" in text and "202" in text:
                examples.append(
                    {
                        "instruction": f"State the combined contract rule described in {rel}.",
                        "response": "Tenant-owned routes must stay organization-scoped and async actions must return 202 with task_id.",
                        "mode": "reasoning",
                        "tags": ["repo", "contract", "unique"],
                    }
                )
        elif path.suffix == ".py":
            try:
                tree = ast.parse(text)
            except Exception:
                continue
            funcs = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            if funcs:
                fname = funcs[0]
                examples.append(
                    {
                        "instruction": f"What does `{fname}` do in {rel}?",
                        "response": f"`{fname}` is part of the implementation in {rel} and should preserve validation, tenant scope, and the documented response shape.",
                        "mode": "general",
                        "tags": ["repo", "code", "unique"],
                    }
                )
                examples.append(
                    {
                        "instruction": f"Write a compact code skeleton for `{fname}` from {rel}.",
                        "response": f"def {fname}(...):\n    pass",
                        "mode": "coding",
                        "tags": ["repo", "code", "unique"],
                    }
                )
            if classes:
                cname = classes[0]
                examples.append(
                    {
                        "instruction": f"Explain the role of `{cname}` in {rel} in one sentence.",
                        "response": f"`{cname}` groups the main logic in {rel} and should keep the surrounding invariants intact.",
                        "mode": "general",
                        "tags": ["repo", "code", "unique"],
                    }
                )
            if "assert" in text and "organization_id" in text:
                examples.append(
                    {
                        "instruction": f"State the testing concern shown in {rel}.",
                        "response": "The test is guarding tenant isolation and preventing cross-organization leakage.",
                        "mode": "reasoning",
                        "tags": ["repo", "test", "unique"],
                    }
                )
        elif path.suffix in {".yaml", ".yml"} and "lora" in path.as_posix():
            examples.append(
                {
                    "instruction": f"Explain how {rel} is used in the training workflow.",
                    "response": "It defines the fine-tuning configuration and should stay aligned with the dataset schema and trainer settings.",
                    "mode": "general",
                    "tags": ["repo", "lora", "unique"],
                }
            )
        elif path.suffix == ".json":
            try:
                data = json.loads(text)
            except Exception:
                data = None
            if isinstance(data, dict) and "paths" in data:
                examples.append(
                    {
                        "instruction": f"Summarize the API contract source stored in {rel}.",
                        "response": "It defines endpoint shapes, response codes, and the contract boundaries that the backend and client should match.",
                        "mode": "summarization",
                        "tags": ["repo", "openapi", "unique"],
                    }
                )
    return examples


def augment(records: list[dict], target: int) -> list[dict]:
    unique: list[dict] = []
    seen: set[str] = set()

    def add(rec: dict) -> None:
        key = record_key(rec)
        if key in seen:
            return
        seen.add(key)
        unique.append(rec)

    for rec in records:
        add(rec)

    for example in synthetic_examples():
        add(example)

    for example in load_repo_mined_examples(Path(".")):
        add(example)

    # Sort by mode to keep the final file predictable and useful for balancing.
    if len(unique) > target:
        return unique[:target]

    # If we still have a gap, allow only distinct source-backed variants,
    # not paraphrases of the same instruction/response pair.
    source_by_mode: dict[str, list[dict]] = {mode: [] for mode in MODES}
    for rec in unique:
        source_by_mode.setdefault(rec.get("mode", "general"), []).append(rec)

    i = 0
    while len(unique) < target and unique:
        mode = MODES[i % len(MODES)]
        candidates = source_by_mode.get(mode) or unique
        rec = candidates[i % len(candidates)]
        candidate = dict(rec)
        candidate["tags"] = list(dict.fromkeys([*(candidate.get("tags", []) or []), "derived", "unique"]))
        candidate["instruction"] = normalize_text(candidate["instruction"])
        candidate["response"] = normalize_text(candidate["response"])
        if record_key(candidate) not in seen:
            seen.add(record_key(candidate))
            unique.append(candidate)
        i += 1

    return unique[:target]


def main() -> int:
    parser = argparse.ArgumentParser(description="Expand the LoRA dataset with synthetic variants.")
    parser.add_argument("--input", default="lora/data/train.jsonl")
    parser.add_argument("--output", default="lora/data/train.augmented.jsonl")
    parser.add_argument("--target", type=int, default=3000)
    args = parser.parse_args()

    records = load_records(Path(args.input))
    augmented = augment(records, args.target)
    dump_records(Path(args.output), augmented)

    counts = Counter(rec.get("mode", "general") for rec in augmented)
    print(f"wrote {len(augmented)} records to {args.output}")
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
