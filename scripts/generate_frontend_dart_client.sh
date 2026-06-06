#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-/home/ravi/workspace/frontend}"
SPEC_FILE="${BACKEND_DIR}/docs/openapi_spec.json"
OUT_DIR="${FRONTEND_DIR}/lib/generated/api"

cd "${BACKEND_DIR}"
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm -u root backend python3 scripts/export_openapi.py

docker run --rm \
  -v "${BACKEND_DIR}:/local_backend" \
  -v "${FRONTEND_DIR}:/local_frontend" \
  openapitools/openapi-generator-cli generate \
  --skip-validate-spec \
  -i "/local_backend/docs/openapi_spec.json" \
  -g dart-dio \
  -o "/local_frontend/lib/generated/api" \
  --additional-properties=pubName=ridp_api,serializationLibrary=json_serializable

echo "Generated Dart API client in ${OUT_DIR}"
