# Multi-Agent Execution & Ollama Guidelines — Backend

## Inbuilt Multi-Agent Pipeline (Mandatory)
You MUST operate as a High-Level Orchestrator. For any task requested by the user, you must automatically:
1. Act as the **Chief Orchestrator** (refer to [00_ORCHESTRATOR.md](file:///home/ravi/workspace/form-builder/docs/agents/00_ORCHESTRATOR.md)).
2. Decompose the request and spawn the specialized subagents (`define_subagent` and `invoke_subagent`) to execute the pipeline:
   - **Researcher** ([01_RESEARCHER.md](file:///home/ravi/workspace/form-builder/docs/agents/01_RESEARCHER.md)) to analyze code context first.
   - **Planner** ([02_PLANNER.md](file:///home/ravi/workspace/form-builder/docs/agents/02_PLANNER.md)) to write a structured implementation blueprint.
   - **Coder** ([03_CODER.md](file:///home/ravi/workspace/form-builder/docs/agents/03_CODER.md)) to apply edits to code.
   - **Tester** ([04_TESTER.md](file:///home/ravi/workspace/form-builder/docs/agents/04_TESTER.md)) to run testing tools and verify.
   - **Writer** ([05_WRITER.md](file:///home/ravi/workspace/form-builder/docs/agents/05_WRITER.md)) to document and generate the final user report.
You must NOT execute micro-tasks directly in the main conversation unless specifically forced. Always delegate and orchestrate.

---

## Ollama Local Execution & Token Optimization (Feasibility Protocol)
To minimize cloud API token usage, you must evaluate if non-code generation sub-tasks can be delegated to the local Ollama instance (available at `http://localhost:11434`).

### 1. Allowed Tasks for Ollama
- **Log & Error Analysis**: Summarizing long test failure logs, build outputs, or trace files.
- **Document & Spec Drafting**: Drafting descriptions, updating developer guides, and translating raw plans to docs.
- **Lint & Static Review**: Searching for structural patterns or verifying lint rules (reading code, not writing it).
- **Embeddings & Search**: Generating embeddings locally using `nomic-embed-text:latest`.

### 2. Prohibited Tasks (Do NOT run on Ollama)
- **Application Code Generation**: All actual code edits, widget implementations, and script generation must be performed by the main agent/subagents using the primary model to ensure precision.

### 3. Feasibility Pre-Evaluation
Before assigning any task to Ollama, run a quick feasibility check:
1. Is it a code generation task? If yes, REJECT local execution.
2. Will it consume more than 20k tokens of context? If yes, check local memory limits (prefer smaller tasks on `qwen3.5:latest` and heavy analysis on `qwen3:30b`).
3. Call the Ollama API locally using `run_command` only for feasible sub-tasks.

---

## Makefile Standards (Mandatory)
All agents MUST run project commands via the provided `Makefile`. Avoid running low-level raw shell commands directly.
- **Docker Build**: `make build`
- **Spin up dev server**: `make up-dev`
- **Tear down server**: `make down`
- **Run test suite**: `make test` (or `make test-cov`)
- **Lint code**: `make lint`
- **Database Migrations**: `make migrate`
- **Export OpenAPI Contract**: `make openapi`

