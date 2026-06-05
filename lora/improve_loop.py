#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


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


def launch_training(fast: bool) -> int:
    cmd = ["python3", "lora/run_llama_factory.py"]
    if fast:
        cmd.append("--fast")
    return run(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuously improve the local LoRA model.")
    parser.add_argument("--cycles", type=int, default=1, help="Number of improvement cycles. Use 0 for infinite.")
    parser.add_argument("--sleep-seconds", type=int, default=60, help="Pause between cycles.")
    parser.add_argument("--target-dataset-size", type=int, default=3000)
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

        if run([
            "python3",
            "lora/augment_dataset.py",
            "--input",
            "lora/data/train.jsonl",
            "--output",
            "lora/data/train.augmented.jsonl",
            "--target",
            str(args.target_dataset_size),
        ]) != 0:
            return 1
        if run([
            "python3",
            "lora/build_train_dataset.py",
            "--source",
            "lora/data/train.augmented.jsonl",
            "--output",
            "lora/data/train.jsonl",
            "--limit-json",
            str(args.target_dataset_size // 5),
            "--limit-coding",
            str(args.target_dataset_size // 5),
            "--limit-reasoning",
            str(args.target_dataset_size // 5),
            "--limit-summarization",
            str(args.target_dataset_size // 5),
            "--limit-general",
            str(args.target_dataset_size // 5),
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
