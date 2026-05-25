# Makefile — form-backend (RIDP platform)

.PHONY: help up up-dev down restart restart-dev logs shell \
        build bootstrap ps test lint openapi generate-dart-client clean backup restore list-backups \
        migrate migrate-local pre-commit-install contract-test

# ANSI colors
CYAN  := \033[36m
GREEN := \033[32m
YELLOW:= \033[33m
RESET := \033[0m

# ─────────────────────────────────────────────
help: ## Show this help
	@echo "$(CYAN)form-backend — RIDP Application$(RESET)"
	@echo "======================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-18s$(RESET) %s\n", $$1, $$2}'

# ─────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────
build: ## Build application image (no cache)
	@echo "$(CYAN)Building form-backend image...$(RESET)"
	@docker compose build --no-cache
	@echo "$(GREEN)✅ Build complete.$(RESET)"

# ─────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────
up: ## Start all services (production)
	@echo "$(CYAN)Starting form-backend...$(RESET)"
	@mkdir -p logs
	@docker compose up -d
	@echo "$(GREEN)✅ Running at http://localhost:$${PORT:-8051}$(RESET)"

up-dev: ## Start in development mode (with live reload)
	@echo "$(CYAN)Starting form-backend (DEV)...$(RESET)"
	@mkdir -p logs
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
	@echo "$(GREEN)✅ Hot-reload enabled via bind-mount to /app$(RESET)"
	@echo "$(GREEN)✅ Logs are being written to ./logs/$(RESET)"

down: ## Stop all services
	@docker compose down

restart: ## Restart backend, worker, beat, and event listener
	@docker compose restart backend celery celery-beat event-listener

restart-dev: ## Restart dev stack services using the dev compose override
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml restart backend celery celery-beat event-listener

logs: ## Follow backend logs
	@docker compose logs -f backend

logs-worker: ## Follow celery worker logs
	@docker compose logs -f celery

ps: ## Show running containers for this app
	@docker compose ps

# ─────────────────────────────────────────────
# Shell & Tools
# ─────────────────────────────────────────────
shell: ## Open shell in backend container
	@docker compose exec backend bash

shell-worker: ## Open shell in celery worker container
	@docker compose exec celery bash

# ─────────────────────────────────────────────
# Bootstrap (provision shared-infra resources)
# ─────────────────────────────────────────────
bootstrap: ## Provision MongoDB indexes (runs a temporary container — no need for make up first)
	@echo "$(CYAN)Bootstrapping form-backend resources...$(RESET)"
	@docker compose run --rm backend python scripts/bootstrap_resources.py
	@echo "$(GREEN)✅ Bootstrap complete.$(RESET)"

# ─────────────────────────────────────────────
# Tests & Linting
# ─────────────────────────────────────────────
test: ## Run test suite
	@docker compose run --rm backend pytest -v

test-cov: ## Run tests with coverage report
	@docker compose run --rm backend pytest --cov=. --cov-report=term-missing

lint: ## Run flake8, black (check), and mypy
	@docker build -t forms-linter -f Dockerfile.linter .
	@docker run --rm forms-linter

openapi: ## Export and validate Swagger/OpenAPI contract
	@python scripts/export_openapi.py

generate-dart-client: ## Generate Flutter Dart API client from the exported contract
	@./scripts/generate_frontend_dart_client.sh

# ─────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────
clean: ## Remove containers and anonymous volumes
	@docker compose down -v --remove-orphans
	@echo "$(GREEN)✅ Cleaned up.$(RESET)"

clean-es: ## Remove Elasticsearch data volume
	@echo "$(YELLOW)⚠️  This will delete all Elasticsearch data!$(RESET)"
	@read -p "Are you sure? [y/N]: " confirm && [ "$$confirm" = "y" ]
	@docker compose down -v --remove-orphans

# ─────────────────────────────────────────────
# Backup & Restore
# ─────────────────────────────────────────────
backup: ## Create a full data backup (MongoDB, DuckDB, Uploads)
	@./scripts/backup_restore.sh backup

restore: ## Restore data from a backup file (Usage: make restore FILE=backups/file.tar.gz)
	@./scripts/backup_restore.sh restore $(FILE)

list-backups: ## List all available backups
	@./scripts/backup_restore.sh list

# ─────────────────────────────────────────────
# Database Migrations
# ─────────────────────────────────────────────
migrate: ## Run all database migrations (inside container)
	@echo "$(CYAN)Running database migrations...$(RESET)"
	@docker compose exec backend python scripts/migrations/001_add_compound_indexes.py
	@echo "$(GREEN)✅ Migrations complete.$(RESET)"

migrate-local: ## Run migrations against local MongoDB (requires MONGODB_URI env)
	@echo "$(CYAN)Running database migrations (local)...$(RESET)"
	@python scripts/migrations/001_add_compound_indexes.py
	@echo "$(GREEN)✅ Migrations complete.$(RESET)"

# ─────────────────────────────────────────────
# Developer Tooling
# ─────────────────────────────────────────────
pre-commit-install: ## Install pre-commit hooks locally
	@pip install pre-commit && pre-commit install
	@echo "$(GREEN)✅ Pre-commit hooks installed.$(RESET)"

contract-test: ## Validate backend routes match frontend expectations
	@echo "$(CYAN)Running contract tests...$(RESET)"
	@docker compose run --rm backend python scripts/contract_test.py
	@echo "$(GREEN)✅ Contract validation complete.$(RESET)"
