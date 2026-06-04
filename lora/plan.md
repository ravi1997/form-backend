# LoRA Fine-Tuning Plan

## Objective
Produce a local assistant that is materially better on the tasks we actually care about:
- reasoning
- code generation
- JSON/schema obedience
- concise instruction following
- long-context summarization

The target is not a generic benchmark win. The target is a useful local assistant that stays above the acceptance threshold on the task mix below.

## Acceptance thresholds
The tuned model is considered promotable only if the evaluation run shows:
- reasoning: `>= 8.5/10`
- coding: `>= 8.5/10`
- JSON/schema compliance: `>= 8.5/10`
- summarization: `>= 8.5/10`
- instruction following / verbosity control: `>= 8.5/10`
- no regression in overall usability versus the current base model

If any category falls below `8.5`, the run is not accepted and the next iteration must change the dataset, prompt template, or training settings before another merge.

## Recommended data mix
- 30% coding tasks
- 30% JSON/schema tasks
- 20% reasoning tasks
- 10% summarization tasks
- 10% project-specific tasks

This mix intentionally overweights structured-output behavior because that is the biggest weakness in the current model behavior.

## Example size targets
- Minimum viable: 300 examples
- First serious run: 1,000 to 2,000 examples
- Strong specialization: 3,000 to 8,000 examples

The quality of the examples matters more than raw count. Small but clean beats large and noisy.

## Dataset rules
1. Keep every response in the target style.
2. Prefer short, correct, repetitive examples.
3. Include exact-format targets:
   - JSON only
   - code only
   - brief answer only
4. Avoid chain-of-thought transcripts.
5. Include correction examples where the response explicitly fixes formatting mistakes.

## Training strategy
1. Start with LoRA or QLoRA, not full fine-tuning.
2. Freeze the base model.
3. Train adapters only.
4. Evaluate after every small checkpoint interval.
5. Keep the best checkpoint only if it improves the category gate list.
6. If structured output regresses, stop and repair the dataset before continuing.

## Suggested hyperparameter starting point
- rank: 16 or 32
- alpha: 32 to 64
- dropout: 0.03 to 0.05
- learning rate: `1e-4` to `2e-4`
- batch size: as large as VRAM allows without instability
- gradient accumulation: use to simulate a larger batch
- context length: match real usage, not the theoretical max

For a 30B-class model, start conservatively and change only one major variable per run.

## Three-phase improvement loop

### Phase 1: behavior shaping
- strengthen instruction following
- reduce verbosity
- reinforce code-first responses
- reinforce valid JSON-only responses

### Phase 2: task specialization
- add repository-specific prompts
- add RIDP-specific code and API examples
- add harder reasoning and debugging examples

### Phase 3: regression control
- compare every new checkpoint against the previous best
- keep a rollback path to the base model
- do not merge if any critical category regresses

## Evaluation gates
- JSON output must parse without repair
- coding answers must compile or run
- reasoning answers must be correct on the benchmark set
- summaries must preserve exact facts
- terse output tasks must not include extra commentary
- benchmark outputs must be stable across repeated runs

## Ollama import path
1. Merge the adapter into the base model or export a merged checkpoint.
2. Place the merged checkpoint in a local directory.
3. Use `lora/Modelfile` to build an Ollama-served variant.
4. Benchmark the served model against the base model and the current tuned model.

## Stop conditions
- If the tuned model is better on reasoning but worse on JSON, keep the base model plus wrapper.
- If the tuned model is better on JSON but worse on reasoning, keep the base model and improve the dataset.
- If the tuned model is better on both reasoning and JSON, promote it.
- If the tuned model regresses broadly, discard the adapter and retrain.
