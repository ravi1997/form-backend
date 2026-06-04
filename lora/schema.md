# Dataset Schema

Use JSONL with one record per line.

Required fields:
- `instruction`: user prompt
- `response`: ideal assistant response

Optional fields:
- `system`: system prompt for the example
- `tags`: array of labels such as `["json", "coding"]`
- `mode`: `reasoning`, `coding`, `json`, `summarization`, `general`

Example:

```json
{"instruction":"Return valid JSON only with keys name and score.","response":"{\"name\":\"Project Alpha\",\"score\":85}","mode":"json","tags":["schema","strict-output"]}
```

Guidelines:
- Keep responses exactly in the style you want the model to learn.
- Include many examples that are short and format-constrained.
- Avoid noisy chain-of-thought traces in training targets.
- Prefer correct, minimal responses over verbose explanations.

