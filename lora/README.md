# LoRA Fine-Tuning Workflow

This directory contains a practical fine-tuning scaffold for a local Ollama-compatible model.

What it provides:
- dataset format guidance
- validation of training examples
- evaluation prompts for reasoning, coding, summarization, and JSON compliance
- a Modelfile template for importing a merged model back into Ollama

What it does not do:
- run the actual trainer for you
- install ML dependencies
- merge LoRA weights

The training step is intentionally external because the exact trainer depends on the stack you choose:
- `llama-factory`
- `unsloth`
- `axolotl`
- `transformers` + `peft`

Included scaffolds:
- `lora/train_unsloth.py`
- `lora/llama_factory.yaml`
- `lora/run_llama_factory.py`
- `lora/generate_dataset.py`
- `lora/augment_dataset.py`
- `lora/improve_loop.py`
- `lora/promote_best_checkpoint.py`
- `lora/evaluate.py`

Training flow:
1. Generate a starter dataset from the repo.
2. Merge it with hand-written examples.
3. Validate the JSONL with `validate_dataset.py`.
4. Run `run_llama_factory.py --validate-only` to verify the training inputs.
5. Install the LoRA stack and start a small LoRA run.
6. Evaluate with `evaluate.py`.
7. Keep the checkpoint only if it clears the category gates in `plan.md`.
8. Add fresh synthetic data with `augment_dataset.py` before the next cycle.
9. Repeat the loop with `improve_loop.py` if you want continuous improvement.

Recommended use:
1. Prepare instruction data in `lora/data/train.jsonl`.
2. Validate it with `python3 lora/validate_dataset.py`.
3. Launch training with `python3 lora/run_llama_factory.py`.
4. Merge or export the adapter.
5. Build a local Ollama model from `lora/Modelfile`.
6. Benchmark with `python3 lora/evaluate.py`.

Continuous improvement:
1. Expand the dataset with `python3 lora/augment_dataset.py --target 10000`.
2. Rebuild and validate the balanced dataset.
3. Launch the loop with `python3 lora/improve_loop.py --fast --keep-running`.
4. Promote the best checkpoint with `python3 lora/promote_best_checkpoint.py`.
5. Keep the loop running under `nohup`, `systemd`, or a tmux session.
