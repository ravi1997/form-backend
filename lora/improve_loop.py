#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter


STATE_PATH = Path("lora/improvement_state.json")


def run(cmd: list[str]) -> int:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, check=False).returncode


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def count_modes(path: Path) -> Counter:
    counts: Counter = Counter()
    if not path.exists():
        return counts
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        rec = json.loads(raw)
        if isinstance(rec, dict):
            counts[rec.get("mode", "general")] += 1
    return counts


def launch_training(fast: bool) -> int:
    cmd = ["python3", "lora/run_llama_factory.py"]
    if fast:
        cmd.append("--fast")
    return run(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuously improve the local LoRA model.")
    parser.add_argument("--cycles", type=int, default=1, help="Number of improvement cycles. Use 0 for infinite.")
    parser.add_argument("--sleep-seconds", type=int, default=60, help="Pause between cycles.")
    parser.add_argument("--target-dataset-size", type=int, default=10000)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--keep-running", action="store_true", help="Run forever even after successful cycles.")
    args = parser.parse_args()

    cycle = 0
    while True:
        cycle += 1
        ts = datetime.now(timezone.utc).isoformat()
        print(f"cycle {cycle} @ {ts}")

        state = read_json(STATE_PATH)
        write_state(
            {
                **state,
                "last_cycle_started_at": ts,
                "cycle": cycle,
                "target_dataset_size": args.target_dataset_size,
            }
        )

        augmented_path = "lora/data/train.augmented.jsonl"
        if run([
            "python3",
            "lora/augment_dataset.py",
            "--input",
            "lora/data/train.jsonl",
            "--output",
            augmented_path,
            "--target",
            str(args.target_dataset_size),
        ]) != 0:
            return 1
        mode_counts = count_modes(Path(augmented_path))
        if run([
            "python3",
            "lora/build_train_dataset.py",
            "--source",
            augmented_path,
            "--output",
            "lora/data/train.jsonl",
            "--limit-json",
            str(mode_counts.get("json", 0)),
            "--limit-coding",
            str(mode_counts.get("coding", 0)),
            "--limit-reasoning",
            str(mode_counts.get("reasoning", 0)),
            "--limit-summarization",
            str(mode_counts.get("summarization", 0)),
            "--limit-general",
            str(mode_counts.get("general", 0)),
        ]) != 0:
            return 1
        if run(["python3", "lora/validate_dataset.py", "lora/data/train.jsonl"]) != 0:
            return 1

        rc = launch_training(args.fast)
        if rc != 0:
            print(f"training exited with code {rc}")
            write_state({**read_json(STATE_PATH), "last_training_exit_code": rc, "last_cycle_finished_at": datetime.now(timezone.utc).isoformat()})
            if not args.keep_running and args.cycles != 0:
                return rc
        else:
            run(["python3", "lora/promote_best_checkpoint.py"])
            write_state(
                {
                    **read_json(STATE_PATH),
                    "last_training_exit_code": rc,
                    "last_cycle_finished_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        if args.cycles and cycle >= args.cycles:
            break
        time.sleep(max(0, args.sleep_seconds))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
