#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TrainingStatus:
    model: str
    output_dir: Path
    total_examples: int
    mode_counts: dict[str, int]
    current_step: int | None
    max_steps: int | None
    epoch: float | None
    loss: float | None
    samples_per_second: float | None
    steps_per_second: float | None
    train_runtime: float | None
    checkpoint_count: int
    hf_incomplete_files: int
    hf_complete_files: int
    hf_log_tail: str | None


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None


def load_yaml_model_name(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        value = data.get("model_name_or_path")
        return value if isinstance(value, str) else None
    except Exception:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_dataset_counts(path: Path) -> tuple[int, dict[str, int]]:
    total = 0
    mode_counts: dict[str, int] = {}
    if not path.exists():
        return total, mode_counts
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        total += 1
        rec = json.loads(raw)
        mode = rec.get("mode", "general")
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
    return total, mode_counts


def read_trainer_state(output_dir: Path) -> dict | None:
    candidates = [
        output_dir / "trainer_state.json",
        output_dir / "checkpoint-last" / "trainer_state.json",
    ]
    for path in candidates:
        state = load_json(path)
        if state:
            return state
    return None


def count_checkpoints(output_dir: Path) -> int:
    if not output_dir.exists():
        return 0
    return sum(1 for p in output_dir.iterdir() if p.is_dir() and p.name.startswith("checkpoint-"))


def find_hf_model_dir(model_name: str) -> Path | None:
    slug = model_name.replace("/", "--")
    base = Path.home() / ".cache" / "huggingface" / "hub" / f"models--{slug}"
    if base.exists():
        return base
    return None


def inspect_hf_cache(model_name: str) -> tuple[int, int, str | None]:
    model_dir = find_hf_model_dir(model_name)
    if model_dir is None:
        return 0, 0, None

    incomplete = 0
    complete = 0
    for path in model_dir.rglob("*"):
        if path.is_file():
            if path.name.endswith(".incomplete"):
                incomplete += 1
            elif path.parent.name != ".locks":
                complete += 1

    log_tail = None
    xet_logs = sorted((Path.home() / ".cache" / "huggingface" / "xet" / "logs").glob("*.log"))
    if xet_logs:
        try:
            tail = xet_logs[-1].read_text(encoding="utf-8", errors="ignore").splitlines()[-20:]
            log_tail = "\n".join(tail) if tail else None
        except Exception:
            log_tail = None

    return incomplete, complete, log_tail


def find_current_process() -> tuple[int | None, str | None]:
    try:
        out = subprocess.check_output(
            "ps -eo pid,args | grep '[l]lamafactory-cli train lora/llama_factory.yaml'",
            shell=True,
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return None, None
    if not out:
        return None, None
    line = out.splitlines()[0]
    pid = int(line.split(None, 1)[0])
    return pid, line


def build_status(dataset: Path, output_dir: Path, config: Path | None = None) -> TrainingStatus:
    total_examples, mode_counts = read_dataset_counts(dataset)
    state = read_trainer_state(output_dir) or {}
    log_history = state.get("log_history", []) if isinstance(state, dict) else []
    last_log = log_history[-1] if log_history else {}

    checkpoint_count = count_checkpoints(output_dir)
    current_step = state.get("global_step") if isinstance(state, dict) else None
    max_steps = state.get("max_steps") if isinstance(state, dict) else None
    epoch = last_log.get("epoch") if isinstance(last_log, dict) else None
    loss = last_log.get("loss") if isinstance(last_log, dict) else None
    samples_per_second = last_log.get("train_samples_per_second") if isinstance(last_log, dict) else None
    steps_per_second = last_log.get("train_steps_per_second") if isinstance(last_log, dict) else None
    train_runtime = last_log.get("train_runtime") if isinstance(last_log, dict) else None
    model = state.get("model_name_or_path", "unknown") if isinstance(state, dict) else "unknown"
    if model == "unknown" and config is not None:
        model = load_yaml_model_name(config) or "unknown"
    hf_incomplete_files, hf_complete_files, hf_log_tail = inspect_hf_cache(model) if model != "unknown" else (0, 0, None)

    return TrainingStatus(
        model=model,
        output_dir=output_dir,
        total_examples=total_examples,
        mode_counts=mode_counts,
        current_step=current_step,
        max_steps=max_steps,
        epoch=epoch,
        loss=loss,
        samples_per_second=samples_per_second,
        steps_per_second=steps_per_second,
        train_runtime=train_runtime,
        checkpoint_count=checkpoint_count,
        hf_incomplete_files=hf_incomplete_files,
        hf_complete_files=hf_complete_files,
        hf_log_tail=hf_log_tail,
    )


def fmt_seconds(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "unknown"
    seconds = max(0.0, seconds)
    mins, secs = divmod(int(seconds + 0.5), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}h {mins}m {secs}s"
    if mins:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def estimate_progress(status: TrainingStatus) -> tuple[str, str]:
    if status.current_step is not None and status.max_steps:
        pct = min(100.0, (status.current_step / status.max_steps) * 100.0)
        if status.steps_per_second and status.max_steps > status.current_step:
            remaining_steps = status.max_steps - status.current_step
            eta = remaining_steps / status.steps_per_second
        elif status.train_runtime and status.current_step > 0:
            avg = status.train_runtime / status.current_step
            eta = avg * max(0, status.max_steps - status.current_step)
        else:
            eta = None
        done_text = f"{status.current_step}/{status.max_steps} steps"
        return f"{pct:.1f}%", f"{done_text}, eta {fmt_seconds(eta)}"

    if status.current_step is not None and status.total_examples:
        # Fallback: assume one full epoch over the dataset when max_steps is absent.
        pct = min(100.0, (status.current_step / status.total_examples) * 100.0)
        return f"{pct:.1f}%", f"{status.current_step}/{status.total_examples} examples seen"

    if status.hf_incomplete_files or status.hf_complete_files:
        total = status.hf_incomplete_files + status.hf_complete_files
        pct = 100.0 * status.hf_complete_files / total if total else 0.0
        detail = f"{status.hf_complete_files}/{total} cache files present"
        if status.hf_incomplete_files:
            detail += f", {status.hf_incomplete_files} downloads still incomplete"
        return f"{pct:.1f}%", detail

    return "unknown", "insufficient trainer state"


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor LlamaFactory fine-tuning progress.")
    parser.add_argument("--dataset", default="lora/data/train.jsonl")
    parser.add_argument("--output-dir", default="lora/llama-factory-output")
    parser.add_argument("--config", default="lora/llama_factory.yaml")
    parser.add_argument("--once", action="store_true", help="Print one status snapshot and exit.")
    parser.add_argument("--interval", type=int, default=10, help="Seconds between refreshes.")
    args = parser.parse_args()

    dataset = Path(args.dataset)
    output_dir = Path(args.output_dir)
    config = Path(args.config)

    while True:
        pid, proc_line = find_current_process()
        status = build_status(dataset, output_dir, config=config)
        progress_pct, progress_detail = estimate_progress(status)

        print("model:", status.model)
        print("process:", proc_line or "not running")
        print("dataset examples:", status.total_examples)
        print("mode counts:", status.mode_counts)
        print("checkpoints:", status.checkpoint_count)
        print("current step:", status.current_step)
        print("epoch:", status.epoch if status.epoch is not None else "unknown")
        print("loss:", status.loss if status.loss is not None else "unknown")
        print("throughput:", {
            "samples_per_second": status.samples_per_second,
            "steps_per_second": status.steps_per_second,
        })
        print("hf cache:", {
            "complete_files": status.hf_complete_files,
            "incomplete_files": status.hf_incomplete_files,
        })
        print("progress:", progress_pct)
        print("detail:", progress_detail)
        if status.hf_log_tail:
            print("hf log tail:")
            print(status.hf_log_tail)
        if pid is not None:
            print("pid:", pid)
        print("-" * 60)

        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
