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
- `lora/evaluate.py`

Training flow:
1. Generate a starter dataset from the repo.
2. Merge it with hand-written examples.
3. Validate the JSONL with `validate_dataset.py`.
4. Run `run_llama_factory.py --validate-only` to verify the training inputs.
5. Install the LoRA stack and start a small LoRA run.
6. Evaluate with `evaluate.py`.
7. Keep the checkpoint only if it clears the category gates in `plan.md`.

Recommended use:
1. Prepare instruction data in `lora/data/train.jsonl`.
2. Validate it with `python3 lora/validate_dataset.py`.
3. Launch training with `python3 lora/run_llama_factory.py`.
4. Merge or export the adapter.
5. Build a local Ollama model from `lora/Modelfile`.
6. Benchmark with `python3 lora/evaluate.py`.
