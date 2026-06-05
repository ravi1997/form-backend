#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def checkpoint_score(path: Path) -> tuple[float, float]:
    state = load_json(path / "trainer_state.json") or {}
    log_history = state.get("log_history", []) if isinstance(state, dict) else []
    last = log_history[-1] if log_history else {}
    eval_loss = last.get("eval_loss")
    train_loss = last.get("loss")
    if isinstance(eval_loss, (int, float)):
        return float(eval_loss), float(train_loss) if isinstance(train_loss, (int, float)) else float(eval_loss)
    if isinstance(train_loss, (int, float)):
        return float(train_loss), float(train_loss)
    return float("inf"), float("inf")


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote the best checkpoint by eval/train loss.")
    parser.add_argument("--output-dir", default="lora/llama-factory-output")
    parser.add_argument("--best-dir", default="lora/best-checkpoint")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    best_dir = Path(args.best_dir)
    checkpoints = sorted(p for p in output_dir.glob("checkpoint-*") if p.is_dir())
    if not checkpoints:
        print("no checkpoints found")
        return 1

    scored = [(checkpoint_score(cp), cp) for cp in checkpoints]
    scored.sort(key=lambda item: item[0])
    best_score, best_cp = scored[0]

    if best_dir.exists():
        shutil.rmtree(best_dir)
    shutil.copytree(best_cp, best_dir)
    (best_dir / "best_checkpoint.json").write_text(
        json.dumps(
            {
                "source_checkpoint": best_cp.name,
                "score": best_score[0],
                "secondary_score": best_score[1],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"promoted {best_cp} -> {best_dir}")
    print(f"score: {best_score[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
