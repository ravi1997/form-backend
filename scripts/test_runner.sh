#!/bin/bash
# Local CI/CD Test Validation Orchestration
# Leverages testcontainers-python to spin up isolated MongoDB/Redis clusters
# completely segregated from active docker-compose state.

set -e

echo "==========================================="
echo " Bootstrapping Enterprise Validation Suite "
echo "==========================================="

if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not running. testcontainers requires the Docker daemon."
    exit 1
fi

echo "🔍 Locating virtual environment..."
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "🧪 Executing secure test runner..."
# The `APP_ENV=testing` param guarantees app configuration routes to dummy shards.
APP_ENV=testing coverage run -m pytest tests/

echo "📊 Generating Execution Fidelity Reports..."
coverage report -m

echo "✅ Validation Execution Complete."
