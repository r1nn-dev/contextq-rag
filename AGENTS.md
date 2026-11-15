# AGENTS.md — ContextQ-RAG

Working rules for AI agents in this repository. To change a rule, edit only this file. Do not add rules to tool-specific files such as `CLAUDE.md`.

This file does not copy rules from the reference documents; it only points to them. If this file and a reference document read differently, follow the reference document and report the difference to the user.

An `AGENTS.md` in a subdirectory also applies to work in that directory and wins on conflict.

The reference documents are written in Korean.

---

## §0 Absolute Rules

1. Follow the reference documents in §4 as the source of truth. Use conversations or earlier sessions as grounds only when the content is reflected in a repository document or decision record.
2. Do not fill in values you could not confirm in a document (dates, Issue numbers, verification results, policy values). Leave them blank and ask the user.
3. Do not create or edit Issues, PRs, or comments on GitHub until the user approves. Do not run `git push`.
4. Never write secrets (API keys, tokens, passwords) to files, commits, Issues, or PRs. Leave example values as `<placeholder>` only.

---

## §1 Before Starting Work

1. Confirm the Issue number. If unknown, ask before working.
2. Read the ADRs in `docs/adr/` related to the task before writing code or documents.
3. Read the reference documents for the kind of work from the table in §4. Do not write code based on a document you have not read.
4. Follow `CONTRIBUTING.md` §1.3 for branch naming. Only propose branch create or switch commands, and run them after the user approves.

---

## §2 Document Rules

- If a decision record (ADR) conflicts with a reference document, follow the latest ADR and report the conflict to the user (document, section, phrase).
- If the task requires a contract change (API spec, ERD, error code, policy), stop implementing and propose the document change first.
- Verify implementation by reading code and configuration files, not PR descriptions.
- Reference document locations as `document > section > phrase`, never as line numbers.

---

## §3 Scope and Prohibitions

- Do not expand the work beyond the scope of the current request. If a change outside the scope is necessary, state the target and reason, and proceed only after the user approves.
- Do not modify files outside the Issue scope. If a change is needed, state the target and reason, and modify only after the user approves.
- Before each commit, show the changed file list and the commit message, and get user approval. Follow `CONTRIBUTING.md` §1.3 for the commit subject format.
- Before each commit, run the per-commit routine in §7. Report only the commands you actually ran, with their results.
- Docs-only commits (no Java or Python source changes): skip `spotlessApply` and `uv run ruff check`.
- Never reference `.env` or `.mcp.json` paths in commit messages, code comments, Issue bodies, or PR bodies.
- After creating a branch, push it immediately and open a Draft PR before starting implementation.

---

## §4 Reference Documents

The source of the document list is `docs/README.md`.

| Work | Read first |
| --- | --- |
| Any work | `docs/adr/` (decisions related to the task) |
| Feature scope, priority | `docs/planning/planning.md` |
| Domain policy, state transitions | `docs/planning/policy.md` |
| RAG pipeline design | `docs/specs/rag-pipeline.md` |
| API contracts | `docs/specs/api-spec.md` |
| DB schema | `docs/specs/db-design.md` |
| Service interfaces | `docs/specs/interfaces.md` |
| Data sources | `docs/planning/data-sources.md` |
| Branches, commits, PRs | `CONTRIBUTING.md` §1.3 |
| Code style, before a commit | `docs/ops/code-convention.md` |
| Package structure | `docs/ops/package-structure.md` |
| Environment variables | `docs/ops/env-reference.md` |
| Local dev setup | `docs/ops/local-setup.md` |
| Deployment | `docs/ops/deployment.md` |
| RAG evaluation | `docs/experiments/evaluation.md` |
| System diagrams | `docs/architecture/diagrams.md` |
| AI collaboration guides | `docs/guides/ai/README.md`, prompts in `docs/guides/ai/prompts/` |

---

## §5 Language

- Reply to the user in Korean. 
- Write all outputs and deliverables (Issues, PRs, commit messages, documents) in Korean. Keep `type(scope):`, code identifiers, and file paths as they are.
- Conduct work internally in English (reasoning, intermediate steps, tool calls).
- Write code comments by `docs/ops/code-convention.md` §3 (comment rules).

---

## §6 Stage Prompts

When the user asks for one of the stages below, read the file first and follow its steps and output format. After each stage's output, wait for the user's approval. Do not move to the next stage on your own.

| Request | Prompt |
| --- | --- |
| Start a session | `docs/guides/ai/prompts/00-session-start.md` |
| Plan a milestone, break down Issues | `docs/guides/ai/prompts/10-plan.md` |
| Write or register an Issue | `docs/guides/ai/prompts/20-issue-write.md` |
| Implement | `docs/guides/ai/prompts/30-implement.md` |
| Self-review, help review a PR | `docs/guides/ai/prompts/40-review.md` |
| Write or register a PR | `docs/guides/ai/prompts/50-pr-write.md` |
| Build or test failure, applying review comments | `docs/guides/ai/prompts/60-troubleshoot.md` |

Use only `docs/guides/ai/review-checklist.md` as the review standard.

---

## §7 Build & Test Commands

### Backend (Spring Boot) — `backend/contextq/`

**Per-commit routine (required before every commit with Java changes):**

```bash
cd backend/contextq
./gradlew spotlessApply         # apply Google Java Format — always run before git add
./gradlew compileJava           # verify main sources compile
./gradlew compileTestJava       # verify test sources compile
```

**Pre-push / pre-PR (required):**

```bash
./gradlew spotlessCheck         # CI runs this — must be green
./gradlew clean test            # full test run
```

### AI Server (FastAPI) — `ai-server/`

**Per-commit routine (required before every commit with Python changes):**

```bash
cd ai-server
uv run ruff check --fix .       # format & lint — always run before git add
uv run mypy src                 # type check — target: src (NOT ai_server)
```

**Pre-push / pre-PR (required):**

```bash
uv run pytest -q                # full test run
```

### Docs-only commit

Skip `spotlessApply` and `uv run ruff check`. No Java or Python changes — no compile or type-check needed.

---

## §8 Architecture Overview

### Runtime topology

```
Browser ──HTTPS──► React (Vite)  [frontend/]
                        │
                        │ REST / SSE
                        │ (SSE: fetch + ReadableStream — NOT EventSource)
                        ▼
         Spring Boot 4.1.2 (Java 21)  :8080  [backend/contextq/]
                        │
                        │ REST  (X-Internal-Token header)
                        ▼
         FastAPI (Python 3.12)  :8000  [ai-server/]
                   │                        │
                   ▼                        ▼
          ChromaDB (embedded)           OpenAI API
          text-embedding-3-small        gpt-4o-mini
```

- Backend validates sessions and forwards RAG requests to ai-server with `X-Internal-Token`.
- SSE streaming: backend relays ai-server SSE to the browser via Spring's `SseEmitter`. See ADR-003.
- ChromaDB runs embedded (no separate process). See ADR-002.
- Frontend is AI-delegated; do not modify `frontend/` without reading `frontend/AGENTS.md` if it exists.

### Backend package layout (`com.r1nn.contextq`)

```
com.r1nn.contextq
├── {domain}/
│   ├── controller/   ← ResponseEntity<ApiResponse<T>>
│   ├── service/      ← @Transactional on public methods; readOnly for reads
│   ├── repository/   ← Spring Data JPA
│   ├── domain/       ← @Entity; protected no-args ctor; static factory; no @Setter/@Builder
│   ├── dto/          ← record; static from(entity) for responses
│   └── client/       ← outbound HTTP (outside any transaction)
└── global/
    ├── config/       ← app-wide config (@ConfigurationProperties, never @Value)
    └── error/        ← GlobalExceptionHandler, AppErrorCode
```

See `docs/ops/code-convention.md` §4 for detailed conventions.

### AI Server package layout (`ai-server/src/`)

Layout is defined by `packages = ["src"]` in `pyproject.toml`.

- Path: `ai-server/src/<module>/` (NOT `ai-server/ai_server/<module>/`)
- Import: `from src.<module> import ...` (NOT `from ai_server.<module> import ...`)
- mypy target: `src` (NOT `ai_server`)

See `docs/ops/package-structure.md` for the full module list and responsibilities.
