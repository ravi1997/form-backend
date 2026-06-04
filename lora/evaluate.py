#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path


BENCHMARKS = [
    {
        "name": "json_compliance",
        "prompt": 'Return valid JSON only with keys name, score, strengths, weaknesses. No commentary.',
        "expect_json": True,
    },
    {
        "name": "reasoning",
        "prompt": (
            "Solve carefully: A 3-digit lock code uses digits 1-9 with no repeats. "
            "Clues: 682 one digit correct and in right place; 614 one digit correct but wrong place; "
            "206 two digits correct but wrong place; 738 nothing correct; 780 one digit correct but wrong place. "
            "What is the code? Answer only with the code."
        ),
        "expect_regex": r"^\d{3}$",
    },
    {
        "name": "coding",
        "prompt": (
            "Write a Python function top_k_words(text, k) that returns the k most common words, "
            "case-insensitive, ignoring punctuation, and breaking ties alphabetically. "
            "Include 3 plain assert tests. Keep it compact and code-first."
        ),
        "must_contain": ["def top_k_words", "assert"],
    },
    {
        "name": "summarization",
        "prompt": (
            "Summarize this in 3 bullet points, preserving facts exactly: "
            "Ollama qwen3:30b is a strong local reasoning model on a machine with 64 CPU cores, 125 GiB RAM, "
            "and an RTX 5090 with 32 GiB VRAM. It is large, slow to download, and verbose by default. "
            "It performs well on reasoning and coding, but it struggles with strict JSON output and terse instruction following."
        ),
        "must_contain": ["64 CPU cores", "125 GiB RAM", "RTX 5090", "strict JSON output"],
    },
]


def run_prompt(model, prompt):
    start = time.perf_counter()
    proc = subprocess.run(
        ["ollama", "run", model],
        input=prompt + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = time.perf_counter() - start
    output = (proc.stdout or "").strip()
    return proc.returncode, output, elapsed, proc.stderr.strip()


def score_benchmark(item, output):
    if item.get("expect_json"):
        try:
            data = json.loads(output)
            ok = isinstance(data, dict) and {"name", "score", "strengths", "weaknesses"} <= set(data)
            return ok, "json-parsed" if ok else "json-missing-keys", 10.0 if ok else 0.0
        except Exception:
            return False, "invalid-json", 0.0
    if "expect_regex" in item:
        ok = bool(re.match(item["expect_regex"], output.strip()))
        return ok, "regex-match" if ok else "regex-miss", 10.0 if ok else 0.0
    if "must_contain" in item:
        missing = [token for token in item["must_contain"] if token not in output]
        if missing:
            penalty = min(10.0, 2.5 * len(missing))
            return False, f"missing:{','.join(missing)}", max(0.0, 10.0 - penalty)
        return True, "ok", 10.0
    return True, "ok", 10.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:30b-elite")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    results = []
    for item in BENCHMARKS:
        code, output, elapsed, err = run_prompt(args.model, item["prompt"])
        ok, detail, score = score_benchmark(item, output)
        results.append(
            {
                "name": item["name"],
                "ok": ok,
                "detail": detail,
                "score": round(score, 2),
                "seconds": round(elapsed, 2),
                "exit_code": code,
                "output": output,
                "stderr": err,
            }
        )

    category_scores = {item["name"]: result["score"] for item, result in zip(BENCHMARKS, results)}
    average_score = round(sum(category_scores.values()) / max(len(category_scores), 1), 2)
    summary = {
        "model": args.model,
        "passed": sum(1 for r in results if r["ok"]),
        "total": len(results),
        "average_score": average_score,
        "category_scores": category_scores,
        "results": results,
    }
    print(json.dumps(summary, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
