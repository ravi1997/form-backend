#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/llama_factory_train.log"

mkdir -p "$LOG_DIR"

cd "$ROOT_DIR"
if [ -x ".venv-lora/bin/llamafactory-cli" ]; then
  .venv-lora/bin/llamafactory-cli train lora/llama_factory.yaml 2>&1 | tee "$LOG_FILE"
else
  llamafactory-cli train lora/llama_factory.yaml 2>&1 | tee "$LOG_FILE"
fi
