# ContextQ-RAG — Makefile
# Shortcut commands for local development.
# Prerequisites: Docker Desktop, uv, node/npm, lefthook

.PHONY: up down logs demo-check ingest activate-index rollback-index smoke-index snapshot-index restore-index eval eval-check eval-tau eval-abstain test hooks help

# --- Docker Compose -------------------------------------------------------

# local override: exposes ports, mounts configs and the host index (ai-server/data/chroma).
# --env-file: Compose reads its env file from the project directory (infra/) by default, not the repo root
COMPOSE_LOCAL = docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.local.yml

up: ## Build and start the full stack with the local override (nginx + backend + ai-server + postgres) → http://localhost
	$(COMPOSE_LOCAL) up -d --build

down: ## Stop full stack
	$(COMPOSE_LOCAL) down

logs: ## Tail container logs
	$(COMPOSE_LOCAL) logs -f

demo-check: ## Pre-demo status check (containers, health, sources, 1 guest question). Usage: make demo-check [ARGS=--no-llm]
	bash scripts/demo-check.sh $(ARGS)

# --- Index build (offline, local·staging only — ADR-005) ------------------
# Requires INGEST_ENABLED=true and APP_PROFILE != prod; DB migrated (alembic upgrade head).

ingest: ## Build a new index run for one source. Usage: make ingest SOURCE=langchain_v1x [STRATEGY=A|B|C] [COMMIT=<40-char sha>]
	cd ai-server && uv run python -m src.ingest.cli ingest --source $(SOURCE) $(if $(STRATEGY),--strategy $(STRATEGY),) $(if $(COMMIT),--commit $(COMMIT),)

activate-index: ## Activate a READY run (READY -> ACTIVE, pointer swap). Usage: make activate-index RUN=<id>
	cd ai-server && uv run python -m src.ingest.cli activate --run $(RUN)

rollback-index: ## Roll back to the previous SUPERSEDED run (1 generation). Usage: make rollback-index SOURCE=<key>
	cd ai-server && uv run python -m src.ingest.cli rollback --source $(SOURCE)

smoke-index: ## Re-run smoke questions on ACTIVE runs with configs/rag.yaml τ (read-only). Usage: make smoke-index [SOURCE=<key>]
	cd ai-server && uv run python -m src.ingest.cli smoke $(if $(SOURCE),--source $(SOURCE),)

snapshot-index: ## Export a READY/ACTIVE/SUPERSEDED run to snapshot-{source}-run{id}.tar.gz (+ .sha256). Usage: make snapshot-index RUN=<id> [OUT=<dir>]
	cd ai-server && uv run python -m src.ingest.cli snapshot --run $(RUN) $(if $(OUT),--out $(OUT),)

# All profiles (prod included): RESTORING -> checksum -> VALIDATING -> READY -> ACTIVE (policy §4.5).
restore-index: ## Restore a snapshot with its run id, validate it and activate it. Usage: make restore-index SNAPSHOT=<path relative to ai-server/ or absolute>
	cd ai-server && uv run python -m src.ingest.cli restore --snapshot $(SNAPSHOT) --activate

# --- Evaluation (docs/experiments/evaluation.md §4) -----------------------
# Needs DB (ACTIVE pointers), CHROMA_DATA_DIR index, OPENAI_API_KEY for query embeddings.
# E1-C uses the service Retriever (ChromaRetriever). E2 searches one READY/ACTIVE/SUPERSEDED run
# per strategy (A, B, C) and source: build them first with `make ingest STRATEGY=...`.

eval: ## Run retrieval eval -> eval/results/{E1,E2}/. Usage: make eval [EXP="E1 E2"] [CONDITIONS="N F C"]
	cd ai-server && uv run python -m src.eval.run --exp $(or $(EXP),E1 E2) $(if $(CONDITIONS),--conditions $(CONDITIONS),)

eval-check: ## Validate eval question sets (schema, v1 composition, review status)
	cd ai-server && uv run python -m src.eval.run --check

eval-tau: ## Decide per-source NO_CONTEXT τ from E1 results (decision_rules §3)
	cd ai-server && uv run python -m src.eval.tau

eval-abstain: ## Two-stage NO_CONTEXT measurement: τ block + LLM_ABSTAIN (real LLM, ~50 calls)
	cd ai-server && uv run python -m src.eval.abstain

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