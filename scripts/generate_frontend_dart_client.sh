#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-/home/ravi/workspace/frontend}"
SPEC_FILE="${BACKEND_DIR}/docs/openapi_spec.json"
OUT_DIR="${FRONTEND_DIR}/lib/generated/api"

cd "${BACKEND_DIR}"
python scripts/export_openapi.py

if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required to generate the Dart client" >&2
  exit 1
fi

npx @openapitools/openapi-generator-cli generate \
  -i "${SPEC_FILE}" \
  -g dart-dio \
  -o "${OUT_DIR}" \
  --additional-properties=pubName=ridp_api,serializationLibrary=json_serializable

echo "Generated Dart API client in ${OUT_DIR}"
