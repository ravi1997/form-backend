#!/usr/bin/env python3
"""
Unsloth training scaffold.

This script intentionally keeps the training logic thin so it can be adapted
to the exact model, dataset, and hardware you choose.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrainConfig:
    model_name: str
    train_file: Path
    eval_file: Path | None
    output_dir: Path
    max_seq_length: int
    max_steps: int | None
    learning_rate: float
    batch_size: int
    grad_accum: int
    lora_rank: int
    lora_alpha: int
    lora_dropout: float
    backend: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LoRA training scaffold for Unsloth.")
    parser.add_argument("--model-name", default="qwen3:30b")
    parser.add_argument("--train-file", default="lora/data/train.jsonl")
    parser.add_argument("--eval-file", default="")
    parser.add_argument("--output-dir", default="lora/unsloth-output")
    parser.add_argument("--max-seq-length", type=int, default=32768)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lora-rank", type=int, default=32)
    parser.add_argument("--lora-alpha", type=int, default=64)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument(
        "--backend",
        choices=["unsloth", "llama-factory"],
        default="llama-factory",
        help="Which external LoRA trainer to invoke when available.",
    )
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="Check whether the local environment has the expected training packages.",
    )
    parser.add_argument(
        "--emit-install-commands",
        action="store_true",
        help="Print suggested install commands for the missing training stack.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved config without starting training.",
    )
    return parser


def package_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def detect_environment() -> dict[str, bool]:
    return {
        "python": True,
        "ollama": shutil.which("ollama") is not None,
        "torch": package_available("torch"),
        "transformers": package_available("transformers"),
        "datasets": package_available("datasets"),
        "peft": package_available("peft"),
        "trl": package_available("trl"),
        "unsloth": package_available("unsloth"),
    }


def resolve_config(args: argparse.Namespace) -> TrainConfig:
    return TrainConfig(
        model_name=args.model_name,
        train_file=Path(args.train_file),
        eval_file=Path(args.eval_file) if args.eval_file else None,
        output_dir=Path(args.output_dir),
        max_seq_length=args.max_seq_length,
        max_steps=args.max_steps or None,
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        grad_accum=args.grad_accum,
        lora_rank=args.lora_rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        backend=args.backend,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = resolve_config(args)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    print("Resolved Unsloth config:")
    for field in config.__dataclass_fields__:
        print(f"- {field}: {getattr(config, field)}")

    if not config.train_file.exists():
        print(f"\nMissing training dataset: {config.train_file}", file=sys.stderr)
        return 1

    env = detect_environment()
    print()
    print("Detected environment:")
    for key, value in env.items():
        print(f"- {key}: {value}")

    if args.emit_install_commands:
        print()
        print("Suggested install commands:")
        print("- python3 -m pip install --upgrade pip")
        print("- python3 -m pip install torch transformers datasets peft trl unsloth")
        print("- ollama pull qwen3:30b")
        print("- ollama pull qwen3.6:latest")
        print("- ollama create qwen3:30b-elite -f Modelfile.qwen3-elite")

    if args.check_env:
        missing = [name for name, available in env.items() if not available and name != "python"]
        if missing:
            print()
            print("Missing packages or tools:")
            for item in missing:
                print(f"- {item}")
            return 1
        print()
        print("Environment check passed.")
        return 0

    if args.dry_run:
        return 0

    backend = config.backend
    if backend == "llama-factory":
        cmd = ["llamafactory-cli", "train", "lora/llama_factory.yaml"]
    else:
        cmd = ["python3", "lora/train_unsloth.py", "--dry-run"]

    print()
    print("Selected training command:")
    print(" ".join(cmd))

    if shutil.which(cmd[0]) is None:
        print(f"Trainer not installed: {cmd[0]}", file=sys.stderr)
        return 2

    result = subprocess.run(cmd, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
