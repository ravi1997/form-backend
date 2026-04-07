#!/bin/bash

# RIDP Form Platform - Postman Runner Script
# This script runs the Postman collection using newman via npx.

# Exit on error
set -e

COLLECTION="postman_collection_updated.json"
ENVIRONMENT="postman_environment_updated.json"
LOG_FILE="postman_run.log"
JSON_RESULTS="postman_results.json"

# Check if collection and environment files exist
if [ ! -f "$COLLECTION" ]; then
    echo "Error: Collection file $COLLECTION not found."
    exit 1
fi

if [ ! -f "$ENVIRONMENT" ]; then
    echo "Error: Environment file $ENVIRONMENT not found."
    exit 1
fi

echo "--------------------------------------------------"
echo "Starting Postman Test Suite..."
echo "Collection: $COLLECTION"
echo "Environment: $ENVIRONMENT"
echo "Logs will be saved to: $LOG_FILE"
echo "JSON results will be saved to: $JSON_RESULTS"
echo "--------------------------------------------------"

# Check if backend is reachable (optional but helpful)
BASE_URL=$(grep -oP '"key": "base_url",\s*"value": "\K[^"]+' "$ENVIRONMENT" | head -1)
if [ -z "$BASE_URL" ]; then
    BASE_URL="http://localhost:8051"
fi

echo "Checking backend health at $BASE_URL/form/health..."
if curl -s --head  --request GET "$BASE_URL/form/health" | grep "200 OK" > /dev/null; then
    echo "Backend is UP!"
else
    echo "Warning: Backend might be DOWN or unreachable at $BASE_URL/form/health."
    echo "Make sure to run 'make up-dev' before starting the tests."
fi

echo "Running tests..."
# Run newman via npx
# --color on: Force color output (useful for tee)
# --reporters cli,json: Generate both console output and machine-readable JSON
# --reporter-json-export: Path to the JSON results file
npx -y newman run "$COLLECTION" \
    -e "$ENVIRONMENT" \
    --reporters cli,json \
    --reporter-json-export "$JSON_RESULTS" \
    --color on 2>&1 | tee "$LOG_FILE"

echo "--------------------------------------------------"
echo "Tests completed."
echo "Please share $LOG_FILE and $JSON_RESULTS if there are issues."
echo "--------------------------------------------------"
