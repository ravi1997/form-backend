---
name: ridp-quality-gates
description: Use before RIDP handoff, commit/PR, after broad refactors, or when asked to verify tests, lint, security, accessibility, OpenAPI, MCP/tooling, or release readiness.
---

# RIDP Quality Gates

Run checks proportional to risk. Report exact commands, failures, skipped checks, and why.

## Fast Gates
```bash
flutter analyze
flutter test
make lint
make test
```

## Contract Gates
```bash
make openapi
make generate-dart-client
schemathesis --version
spectral --version
oasdiff version
```

## Security Gates
```bash
gitleaks detect --source .
semgrep --version
trivy --version
```

## Tooling Gate
```bash
.agents/check-agent-tools.sh
```

Use targeted tests while iterating; run broader gates when touching auth, tenancy, generated clients, shared services, layout engine, or release-critical behavior.
