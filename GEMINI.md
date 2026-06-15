# Agent Instructions — Form Builder Backend

> **Repo**: `/home/ravi/workspace/docker/apps/form-backend`
> **Stack**: Python · Flask · MongoDB · Celery · Redis

---

## Codebase Knowledge Graph (codebase-memory-mcp)

**ALWAYS prefer MCP graph tools over grep/glob/file-search for code discovery.**

### Priority Order
1. `search_graph` — find functions, classes, routes, variables by pattern
2. `trace_path` — trace who calls a function or what it calls
3. `get_code_snippet` — read specific function/class source code
4. `query_graph` — run Cypher queries for complex patterns
5. `get_architecture` — high-level project summary

### When to fall back to grep/glob
- Searching for string literals, error messages, config values
- Searching non-code files (Dockerfiles, shell scripts, configs)
- When MCP tools return insufficient results

### Examples
```
search_graph(name_pattern=".*FormRoute.*")
trace_path(function_name="submit_form", direction="inbound")
get_code_snippet(qualified_name="services.form_service.create_form")
```

### Token-Saving Rules
- Use `get_code_snippet` instead of `view_file` for function lookups — saves ~70–90% tokens
- Use `trace_path` instead of grep chains to find callers/callees
- Open a session with `get_architecture(aspects=["modules","patterns","dependencies"])`
- Do NOT read entire files to answer a scoped question; query the graph first

---

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

## Session Startup (Do This First)
1. `manage_adr(mode="get", repo_path="/home/ravi/workspace/docker/apps/form-backend")` — load persisted decisions
2. `get_architecture(aspects=["modules","patterns","dependencies"])` — prime structure
3. `detect_changes(repo_path="/home/ravi/workspace/docker/apps/form-backend")` — scope to what changed
4. Then use `search_graph` / `get_code_snippet` for targeted lookups


---

## Tool Routing
- **Library / framework docs** → `context7` first, NOT web search or manual file reads
- **Recent changes** → `git_diff(repo="...", ref="HEAD~1")` NOT reading individual files
- **Complex or cross-repo tasks** → `sequential-thinking` BEFORE opening any files
- **Debugging a call chain** → `trace_path` NOT manual grep chains

---

## Project Structure

| Layer | Path | Notes |
|---|---|---|
| Routes / Controllers | `app/routes/` | Flask blueprints; keep thin |
| Business Logic | `app/services/` | PyMongo, transactional steps |
| Core Algorithms | `app/engines/` | Pandas, NetworkX |
| Background Workers | `app/tasks/` + `workers/` | Celery tasks (both dirs exist) |
| Schemas | `app/schemas/` | Pydantic request/response models |
| Models | `models/` | MongoDB collection wrappers |
| Tests | `tests/` | pytest + mongomock (TDD) |

---

## Engineering Guardrails

### Multi-Tenant Query Isolation (Critical)
Every MongoDB query (except `system_config` and `compliance_standards`) MUST include:
```python
query = {"org_id": current_org_id, "is_deleted": False}
```
Never execute a raw `.find()` or `.update_one()` without this scoping filter.

### Architecture Rules
- Routes must stay thin — delegate all business logic to services
- All public methods and route handlers require type hints
- Conform to PEP 8; formatting enforced via `black`
- Use Pydantic models for all request/response serialization
- Plugin subprocesses must never receive `SECRET_KEY`, `REDIS_URL`, or DB credentials

### TDD Workflow
Write `pytest` + `mongomock` unit tests **before** writing endpoint code.

### After Every Edit
Run `python -m pytest tests/ -x -q` and confirm no regressions before closing a task.

---

## Canonical Cross-Repo Paths
- **Docs**: `/home/ravi/workspace/form-builder/docs`
- **Backend**: `/home/ravi/workspace/docker/apps/form-backend`
- **Frontend**: `/home/ravi/workspace/frontend`
- **Shared specs**: `/home/ravi/workspace/form-builder/docs/03_API_SPECIFICATION.md`

---

## Common Failure Modes
- Forgetting `org_id` scoping → cross-tenant data leak
- Reading entire files instead of using graph snippets → token waste
- Changing route response shape without updating Pydantic schema → client breakage
- Running migrations without checking the active `org_id` context
