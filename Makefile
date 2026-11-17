# ContextQ-RAG — Makefile
# Shortcut commands for local development.
# Prerequisites: Docker Desktop, uv, node/npm, lefthook

.PHONY: up down logs ingest activate-index test hooks help

# --- Docker Compose -------------------------------------------------------

up: ## Start full stack (ai-server + backend + frontend + postgres + chroma)
	docker compose -f infra/docker-compose.yml up -d

down: ## Stop full stack
	docker compose -f infra/docker-compose.yml down

logs: ## Tail container logs
	docker compose -f infra/docker-compose.yml logs -f

# --- Index build (offline, local·staging only — ADR-005) ------------------
# Requires INGEST_ENABLED=true and APP_PROFILE != prod; DB migrated (alembic upgrade head).

ingest: ## Build a new index run for one source. Usage: make ingest SOURCE=langchain_v1x [STRATEGY=A|B|C]
	cd ai-server && uv run python -m src.ingest.cli ingest --source $(SOURCE) $(if $(STRATEGY),--strategy $(STRATEGY),)

activate-index: ## Activate a READY run (READY -> ACTIVE, pointer swap). Usage: make activate-index RUN=<id>
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