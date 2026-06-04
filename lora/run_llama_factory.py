#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and launch the LlamaFactory LoRA job.")
    parser.add_argument("--config", default="lora/llama_factory.yaml")
    parser.add_argument("--dataset", default="lora/data/train.jsonl")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use the throughput-oriented LlamaFactory config settings.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate inputs and print the launch command without starting training.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = Path(args.config)
    dataset = Path(args.dataset)

    if not config.exists():
        print(f"Missing config: {config}", file=sys.stderr)
        return 1
    if not dataset.exists():
        print(f"Missing dataset: {dataset}", file=sys.stderr)
        return 1

    if args.fast:
        print("Fast profile enabled: use the throughput-tuned LlamaFactory config.")

    validate_cmd = ["python3", "lora/validate_dataset.py", str(dataset)]
    venv_bin = Path(".venv-lora/bin")
    launch_bin = venv_bin / "llamafactory-cli"
    if launch_bin.exists():
        launch_cmd = [str(launch_bin), "train", str(config)]
    else:
        launch_cmd = ["llamafactory-cli", "train", str(config)]

    print("Validation command:")
    print(" ".join(validate_cmd))
    print("Launch command:")
    print(" ".join(launch_cmd))

    if args.validate_only:
        return 0

    result = subprocess.run(validate_cmd, check=False)
    if result.returncode != 0:
        return result.returncode

    if shutil.which(launch_cmd[0]) is None and not Path(launch_cmd[0]).exists():
        print(f"Trainer not installed: {launch_cmd[0]}", file=sys.stderr)
        return 2

    return subprocess.run(launch_cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
