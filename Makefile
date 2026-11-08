# ContextQ-RAG — Makefile
# Shortcut commands for local development.
# Prerequisites: Docker Desktop, uv, node/npm, lefthook

.PHONY: up down logs build-index activate-index test hooks help

# --- Docker Compose -------------------------------------------------------

up: ## Start full stack (ai-server + backend + frontend + postgres + chroma)
	docker compose -f infra/docker-compose.yml up -d

down: ## Stop full stack
	docker compose -f infra/docker-compose.yml down

logs: ## Tail container logs
	docker compose -f infra/docker-compose.yml logs -f

# --- Index build (offline, local only) ------------------------------------

build-index: ## Collect docs → chunk → embed → store in Chroma (local build only, never on prod)
	# TODO: implement after ai-server/ scripts are created
	@echo "build-index: not yet implemented"

activate-index: ## Update ACTIVE_RUN_ID in .env to the latest run
	# TODO: implement after scripts/activate_index.py is created
	@echo "activate-index: not yet implemented"

# --- Tests ----------------------------------------------------------------

test: ## Run all unit tests (excludes LLM calls and eval suite)
	# TODO: implement after ai-server/ and backend/ are created
	@echo "test: not yet implemented"

# --- Git hooks ------------------------------------------------------------

hooks: ## Install lefthook git hooks
	lefthook install

# --- Help -----------------------------------------------------------------

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help