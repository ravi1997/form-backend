#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ALLOWED_SUFFIXES = {".py", ".md", ".txt", ".yaml", ".yml", ".json"}


@dataclass(frozen=True)
class Example:
    instruction: str
    response: str
    mode: str
    tags: list[str]
    system: str | None = None

    def to_record(self) -> dict:
        record = {
            "instruction": self.instruction,
            "response": self.response,
            "mode": self.mode,
            "tags": self.tags,
        }
        if self.system:
            record["system"] = self.system
        return record


def iter_text_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in ALLOWED_SUFFIXES:
            if "lora/data" in path.as_posix():
                continue
            yield path


def clean_text(text: str, limit: int = 1200) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def hash_key(*parts: str) -> str:
    digest = hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def extract_headings(md_text: str) -> list[str]:
    headings = []
    for line in md_text.splitlines():
        m = re.match(r"^\s{0,3}(#{1,3})\s+(.+?)\s*$", line)
        if m:
            headings.append(m.group(2).strip())
    return headings


def load_openapi_spec(root: Path) -> dict:
    candidates = [
        root / "docs" / "openapi.yaml",
        root / "docs" / "openapi.yml",
        root / "docs" / "openapi_spec.json",
        root / "docs" / "openapi.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        if path.suffix in {".yaml", ".yml"}:
            try:
                import yaml

                return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
        if path.suffix == ".json":
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def schema_summary(schema: dict) -> str:
    if not isinstance(schema, dict):
        return "untyped payload"
    parts: list[str] = []
    for field, meta in schema.get("properties", {}).items():
        if not isinstance(meta, dict):
            continue
        field_type = meta.get("type")
        if not field_type and "enum" in meta:
            field_type = "enum"
        if not field_type and "anyOf" in meta:
            field_type = "nullable"
        parts.append(f"{field}:{field_type or 'object'}")
    return ", ".join(parts[:8]) if parts else "untyped payload"


def status_code_note(status_map: dict) -> str:
    codes = sorted(str(code) for code in status_map.keys())
    return ", ".join(codes[:6]) if codes else "no documented status codes"


def make_openapi_examples(spec: dict) -> list[Example]:
    examples: list[Example] = []
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return examples

    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, meta in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(meta, dict):
                continue

            tags = meta.get("tags") or []
            op_id = meta.get("operationId") or f"{method.upper()} {path}"
            summary = meta.get("summary") or meta.get("description") or op_id
            responses = meta.get("responses") or {}
            request_body = meta.get("requestBody") or {}
            content = request_body.get("content") if isinstance(request_body, dict) else {}

            instruction = f"Document the API contract for {method.upper()} {path}."
            response = (
                f"{summary.strip()} The documented status codes are {status_code_note(responses)}. "
                f"If a request body is expected, its shape should be treated as a contract source."
            )
            examples.extend(
                [
                    Example(
                        instruction=instruction,
                        response=response,
                        mode="summarization",
                        tags=["ridp", "openapi", *[str(tag) for tag in tags][:3]],
                    ),
                    Example(
                        instruction=f"Summarize the request/response contract for {method.upper()} {path} in JSON only.",
                        response=json.dumps(
                            {
                                "method": method.upper(),
                                "path": path,
                                "summary": clean_text(summary, 180),
                                "status_codes": status_code_note(responses),
                            }
                        ),
                        mode="json",
                        tags=["ridp", "openapi", "json"],
                    ),
                    Example(
                        instruction=f"Explain the primary safety or auth concern for {method.upper()} {path}.",
                        response=(
                            "The route should preserve its documented auth boundary, tenant isolation, and response envelope."
                        ),
                        mode="reasoning",
                        tags=["ridp", "openapi", "auth"],
                    ),
                    Example(
                        instruction=f"Write a compact client helper outline for {method.upper()} {path} in code only.",
                        response=(
                            "def call_api(...):\n"
                            "    \"\"\"Call the endpoint and handle the documented status codes.\"\"\"\n"
                            "    pass"
                        ),
                        mode="coding",
                        tags=["ridp", "openapi", "coding"],
                    ),
                    Example(
                        instruction=f"State the implementation principle for {method.upper()} {path} in one sentence.",
                        response="Keep the handler aligned with the documented status codes, auth boundary, and tenant scope.",
                        mode="general",
                        tags=["ridp", "openapi", "general"],
                    ),
                ]
            )

            if method.lower() in {"post", "put", "patch"} and content:
                json_schema = None
                for media in content.values():
                    if isinstance(media, dict):
                        schema = media.get("schema")
                        if isinstance(schema, dict):
                            json_schema = schema
                            break
                if json_schema:
                    examples.extend(
                        [
                            Example(
                                instruction=f"List the expected fields for {method.upper()} {path} in JSON only.",
                                response=json.dumps(
                                    {
                                        "path": path,
                                        "method": method.upper(),
                                        "fields": schema_summary(json_schema),
                                        "status_codes": status_code_note(responses),
                                    }
                                ),
                                mode="json",
                                tags=["ridp", "openapi", "json"],
                            ),
                            Example(
                                instruction=f"State the validation focus for the request body of {method.upper()} {path}.",
                                response=(
                                    f"The request body should validate the schema fields {schema_summary(json_schema)} before reaching the service layer."
                                ),
                                mode="reasoning",
                                tags=["ridp", "openapi", "validation"],
                            ),
                        ]
                    )

            if any(code in responses for code in ("202", 202)):
                examples.extend(
                    [
                        Example(
                            instruction=f"Explain the async contract for {method.upper()} {path}.",
                            response=(
                                "The endpoint returns HTTP 202 for an async operation and should expose a task identifier for polling."
                            ),
                            mode="reasoning",
                            tags=["ridp", "openapi", "async"],
                        ),
                        Example(
                            instruction=f"Write the client-facing shape for the async response from {method.upper()} {path} in JSON only.",
                            response=json.dumps(
                                {"status_code": 202, "body": {"task_id": "string"}}
                            ),
                            mode="json",
                            tags=["ridp", "openapi", "async", "json"],
                        ),
                    ]
                )

            if "security" in meta and meta["security"]:
                examples.extend(
                    [
                        Example(
                            instruction=f"What auth expectation is implied by {method.upper()} {path}?",
                            response="The route is protected and should be treated as authenticated unless the spec explicitly marks it public.",
                            mode="general",
                            tags=["ridp", "openapi", "auth"],
                        ),
                        Example(
                            instruction=f"State the auth rule for {method.upper()} {path} as a short policy sentence.",
                            response="This endpoint requires authenticated access unless the OpenAPI spec clearly marks it as public.",
                            mode="general",
                            tags=["ridp", "openapi", "auth"],
                        ),
                    ]
                )

            if "organization_id" in json.dumps(meta):
                examples.extend(
                    [
                        Example(
                            instruction=f"Summarize the tenant expectation for {method.upper()} {path} in one sentence.",
                            response="Tenant-owned data should be looked up with `organization_id` to preserve isolation.",
                            mode="general",
                            tags=["ridp", "openapi", "tenant-isolation"],
                        ),
                        Example(
                            instruction=f"Explain why `organization_id` matters for {method.upper()} {path}.",
                            response="It prevents cross-tenant access and keeps the operation aligned with the tenant-scoped backend contract.",
                            mode="reasoning",
                            tags=["ridp", "openapi", "tenant-isolation"],
                        ),
                    ]
                )
    return examples


def make_doc_examples(path: Path, text: str) -> list[Example]:
    examples: list[Example] = []
    basename = path.name
    lower = text.lower()

    if "organization_id" in lower and "tenant" in lower:
        examples.extend(
            [
                Example(
                    instruction=f"Explain the tenant isolation rule described in {basename} in 2 bullets.",
                    response=(
                        "- Every tenant-owned query must include `organization_id`.\n"
                        "- `superadmin` is the only cross-organization exception."
                    ),
                    mode="summarization",
                    tags=["ridp", "tenant-isolation", "docs"],
                ),
                Example(
                    instruction=f"Restate the tenant boundary from {basename} as a single policy sentence.",
                    response="All tenant-owned data access must be scoped by `organization_id`, with `superadmin` as the only cross-org exception.",
                    mode="general",
                    tags=["ridp", "tenant-isolation", "docs"],
                ),
            ]
        )

    if "202" in text and "task_id" in lower:
        examples.extend(
            [
                Example(
                    instruction=f"Describe the async API contract in {basename} as a strict implementation note.",
                    response=(
                        "Async routes must return HTTP 202 with `{ \"task_id\": \"...\" }`, "
                        "and the long-running work must be offloaded to Celery rather than a thread."
                    ),
                    mode="reasoning",
                    tags=["ridp", "async", "celery", "docs"],
                ),
                Example(
                    instruction=f"Summarize the async contract from {basename} in JSON only.",
                    response=json.dumps(
                        {
                            "status_code": 202,
                            "async_marker": "task_id",
                            "execution": "Celery",
                        }
                    ),
                    mode="json",
                    tags=["ridp", "async", "celery", "json"],
                ),
            ]
        )

    if "audit_logger" in lower:
        examples.extend(
            [
                Example(
                    instruction=f"State the logging rule implied by {basename}.",
                    response=(
                        "State changes should be written through `audit_logger`, and exceptions should use "
                        "`error_logger.error(..., exc_info=True)`."
                    ),
                    mode="general",
                    tags=["ridp", "logging", "compliance"],
                ),
                Example(
                    instruction=f"Why does {basename} care about audit logging?",
                    response="It captures compliance-relevant state changes so operators can trace important mutations.",
                    mode="reasoning",
                    tags=["ridp", "logging", "compliance"],
                ),
            ]
        )

    if "pydantic v2" in lower or "pydantic" in lower:
        examples.extend(
            [
                Example(
                    instruction=f"What does {basename} imply about request validation?",
                    response=(
                        "All service input must be validated with Pydantic v2 before it reaches the service layer."
                    ),
                    mode="general",
                    tags=["ridp", "validation", "pydantic"],
                ),
                Example(
                    instruction=f"Return the validation rule from {basename} in JSON only.",
                    response=json.dumps(
                        {
                            "validation": "Pydantic v2",
                            "scope": "service input before business logic",
                            "benefit": "reject invalid payloads early",
                        }
                    ),
                    mode="json",
                    tags=["ridp", "validation", "pydantic", "json"],
                ),
            ]
        )

    if "require_roles" in lower or "rbac" in lower:
        examples.extend(
            [
                Example(
                    instruction=f"Summarize the permission model described in {basename} in JSON only.",
                    response=json.dumps(
                        {
                            "roles": ["user", "manager", "admin", "superadmin"],
                            "rule": "Higher roles subsume lower roles",
                            "exception": "superadmin may cross organization boundaries",
                        }
                    ),
                    mode="json",
                    tags=["ridp", "rbac", "json"],
                ),
                Example(
                    instruction=f"State the RBAC rule from {basename} as a one-line policy.",
                    response="A user must possess one of the required roles, with higher roles subsuming lower permissions.",
                    mode="general",
                    tags=["ridp", "rbac"],
                ),
            ]
        )

    if path.suffix in {".md", ".txt"}:
        headings = extract_headings(text)
        if headings:
            examples.extend(
                [
                    Example(
                        instruction=f"List the top 3 concepts covered in {basename}.",
                        response="\n".join(f"- {h}" for h in headings[:3]),
                        mode="summarization",
                        tags=["ridp", "docs"],
                    ),
                    Example(
                        instruction=f"Write a concise policy summary for {basename}.",
                        response=f"{headings[0]} governs the primary behavior, and the rest refine the implementation constraints.",
                        mode="general",
                        tags=["ridp", "docs"],
                    ),
                ]
            )

    return examples


def make_code_examples(path: Path, text: str) -> list[Example]:
    examples: list[Example] = []
    try:
        tree = ast.parse(text)
    except Exception:
        return examples

    functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    lower = text.lower()

    if functions and ("success_response" in lower or "error_response" in lower):
        examples.extend(
            [
                Example(
                    instruction=f"Write a short implementation note for {path.name} focusing on response envelopes.",
                    response=(
                        "Routes should return the canonical success/error envelopes from `utils.response_helper` "
                        "instead of hand-rolling JSON."
                    ),
                    mode="coding",
                    tags=["ridp", "responses", "routes"],
                ),
                Example(
                    instruction=f"State the response-envelope rule shown by {path.name} in JSON only.",
                    response=json.dumps(
                        {
                            "success": "use success_response",
                            "error": "use error_response",
                            "benefit": "consistent client parsing",
                        }
                    ),
                    mode="json",
                    tags=["ridp", "responses", "json"],
                ),
                Example(
                    instruction=f"Write a tiny route wrapper pattern suggested by {path.name}.",
                    response=(
                        "def handler():\n"
                        "    try:\n"
                        "        return success_response(data={})\n"
                        "    except Exception as exc:\n"
                        "        return error_response(message=str(exc), status_code=400)"
                    ),
                    mode="coding",
                    tags=["ridp", "responses", "routes", "coding"],
                ),
            ]
        )

    if "organization_id" in lower:
        examples.extend(
            [
                Example(
                    instruction=f"Identify the tenant-safety requirement that {path.name} demonstrates.",
                    response=(
                        "Tenant-owned lookups must include `organization_id` explicitly, especially for `get()` calls."
                    ),
                    mode="reasoning",
                    tags=["ridp", "tenant-isolation", "code"],
                ),
                Example(
                    instruction=f"Turn the tenant-safety rule in {path.name} into JSON only.",
                    response=json.dumps(
                        {
                            "scope": "tenant-owned lookup",
                            "required_field": "organization_id",
                            "risk": "cross-tenant leakage",
                        }
                    ),
                    mode="json",
                    tags=["ridp", "tenant-isolation", "json"],
                ),
                Example(
                    instruction=f"Show the code pattern that {path.name} is enforcing.",
                    response=(
                        "resource = Model.objects.get(id=item_id, organization_id=current_user.organization_id)\n"
                        "if not resource:\n"
                        "    raise DoesNotExist"
                    ),
                    mode="coding",
                    tags=["ridp", "tenant-isolation", "coding"],
                ),
            ]
        )

    if "task_id" in lower and "202" in text:
        examples.extend(
            [
                Example(
                    instruction=f"Convert the async pattern in {path.name} into a compact coding guideline.",
                    response=(
                        "Async operations should return `202`, emit a `task_id`, and expose status through a polling route."
                    ),
                    mode="coding",
                    tags=["ridp", "async", "task-id"],
                ),
                Example(
                    instruction=f"Represent the async contract in {path.name} as JSON only.",
                    response=json.dumps(
                        {"status_code": 202, "task_id": "string", "polling": True}
                    ),
                    mode="json",
                    tags=["ridp", "async", "json"],
                ),
                Example(
                    instruction=f"Sketch the code flow implied by {path.name}.",
                    response=(
                        "task = task_service.start(...)\n"
                        "return success_response(data={\"task_id\": task.id}, status_code=202)"
                    ),
                    mode="coding",
                    tags=["ridp", "async", "coding"],
                ),
            ]
        )

    if functions or classes:
        focus = functions[0] if functions else classes[0]
        examples.extend(
            [
                Example(
                    instruction=f"Explain the purpose of `{focus}` in {path.name} in one sentence.",
                    response=(
                        f"`{focus}` is part of the route/service logic in {path.name} and should preserve tenant scoping, validation, and canonical responses."
                    ),
                    mode="general",
                    tags=["ridp", "code"],
                ),
                Example(
                    instruction=f"Describe the implementation constraint for `{focus}` in {path.name}.",
                    response="Keep the function thin, validate inputs before service logic, and preserve tenant scoping.",
                    mode="reasoning",
                    tags=["ridp", "code"],
                ),
                Example(
                    instruction=f"Write a minimal code skeleton for `{focus}` in {path.name}.",
                    response=(
                        f"def {focus}(...):\n"
                        f"    \"\"\"{clean_text(text, 120)}\"\"\"\n"
                        "    pass"
                    ),
                    mode="coding",
                    tags=["ridp", "code", "coding"],
                ),
            ]
        )

    return examples


def make_test_examples(path: Path, text: str) -> list[Example]:
    examples: list[Example] = []
    lower = text.lower()

    if "assert response.status_code == 200" in lower or "success_response" in lower:
        examples.extend(
            [
                Example(
                    instruction=f"Turn the intent of {path.name} into a test-writing guideline.",
                    response=(
                        "Tests should validate the canonical response envelope, status codes, and the tenant or role boundary being exercised."
                    ),
                    mode="reasoning",
                    tags=["ridp", "tests"],
                ),
                Example(
                    instruction=f"Summarize the test contract in {path.name} as JSON only.",
                    response=json.dumps(
                        {
                            "assertion_focus": "status code and envelope",
                            "boundary": "tenant or role",
                            "risk": "regression in API contract",
                        }
                    ),
                    mode="json",
                    tags=["ridp", "tests", "json"],
                ),
                Example(
                    instruction=f"Write a compact pytest pattern suggested by {path.name}.",
                    response=(
                        "def test_endpoint(client):\n"
                        "    resp = client.get('/endpoint')\n"
                        "    assert resp.status_code == 200"
                    ),
                    mode="coding",
                    tags=["ridp", "tests", "coding"],
                ),
            ]
        )

    if "organization_id" in lower and "assert" in lower:
        examples.extend(
            [
                Example(
                    instruction=f"Summarize the tenant-isolation coverage in {path.name} in JSON only.",
                    response=json.dumps(
                        {
                            "focus": "tenant isolation",
                            "assertion_style": "queries and endpoints are scoped to organization_id",
                            "risk": "cross-tenant leakage if scoping is missing",
                        }
                    ),
                    mode="json",
                    tags=["ridp", "tests", "tenant-isolation"],
                ),
                Example(
                    instruction=f"State the failure mode covered by {path.name}.",
                    response="It guards against tenant-scoping regressions that could expose another organization’s data.",
                    mode="reasoning",
                    tags=["ridp", "tests", "tenant-isolation"],
                ),
            ]
        )

    return examples


def generate_examples(root: Path, limit: int) -> list[dict]:
    examples: list[Example] = []
    seen: set[str] = set()
    spec = load_openapi_spec(root)
    if spec:
        for example in make_openapi_examples(spec):
            key = hash_key(example.instruction, example.response, example.mode)
            if key in seen:
                continue
            seen.add(key)
            examples.append(example)
            if 0 < limit <= len(examples):
                return [ex.to_record() for ex in examples]

    for path in iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        candidates: list[Example] = []
        if path.suffix in {".md", ".txt"}:
            candidates.extend(make_doc_examples(path, text))
        elif path.suffix == ".py":
            candidates.extend(make_code_examples(path, text))
        elif path.suffix == ".json":
            if "postman" in path.name.lower():
                candidates.append(
                    Example(
                        instruction=f"State the API contract significance of {path.name}.",
                        response=(
                            "Use it as a source of truth for route shape, payload fields, and response envelopes."
                        ),
                        mode="general",
                        tags=["ridp", "api-contract"],
                    )
                )
        elif path.suffix in {".yaml", ".yml"}:
            if "lora" in path.as_posix():
                candidates.append(
                    Example(
                        instruction=f"Explain how {path.name} should be used in the fine-tuning workflow.",
                        response="It should serve as the trainer configuration for LoRA SFT and be kept in sync with the dataset schema.",
                        mode="general",
                        tags=["lora", "training"],
                    )
                )

        if path.suffix == ".py":
            try:
                parsed = ast.parse(text)
                names = [node.name for node in ast.walk(parsed) if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
                if "test" in path.parts or path.name.startswith("test_"):
                    candidates.extend(make_test_examples(path, text))
                elif names:
                    candidates.append(
                        Example(
                            instruction=f"Summarize the main responsibility of {path.name} in 2 bullets.",
                            response=(
                                f"- {path.name} contains {', '.join(names[:2])} and related control flow.\n"
                                f"- It should preserve RIDP invariants: tenant isolation, validation, and canonical responses."
                            ),
                            mode="summarization",
                            tags=["ridp", "code", "summary"],
                        )
                    )
            except Exception:
                continue

        for example in candidates:
            key = hash_key(example.instruction, example.response, example.mode)
            if key in seen:
                continue
            seen.add(key)
            examples.append(example)
            if 0 < limit <= len(examples):
                return [ex.to_record() for ex in examples]

    return [ex.to_record() for ex in examples]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a RIDP-specific LoRA dataset from this repo.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="lora/data/generated.ridp.jsonl")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    root = Path(args.root)
    records = generate_examples(root, args.limit)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"wrote {len(records)} examples to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
