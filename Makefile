# Makefile — form-backend (RIDP platform)

.PHONY: help up up-dev down restart logs shell \
        build bootstrap ps test lint clean

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
	@docker compose up -d
	@echo "$(GREEN)✅ Running at http://localhost:$${PORT:-8051}$(RESET)"

up-dev: ## Start in development mode (with live reload)
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

down: ## Stop all services
	@docker compose down

restart: ## Restart backend and worker only
	@docker compose restart backend celery celery-beat

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
