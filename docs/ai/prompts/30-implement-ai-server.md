# 30. Implement — ai-server

## Purpose

Implement a confirmed Issue scope in `ai-server/` one commit at a time, with approval before each commit.

## When to use

After the user approves the stage 00 report and the stage 10 commit plan.

## Inputs

- Issue number and settled scope from stages 00 and 10
- ADRs and reference documents identified in stage 00
- `docs/specs/rag-pipeline.md` — retrieval chain, source adapters, τ thresholds
- `docs/specs/interfaces.md` — X-Internal-Token, Backend ↔ ai-server request/response schema
- `docs/ops/code-convention.md` — Python style, `src/` layout, uv usage
- `configs/rag.yaml` — τ thresholds, top-k, model names, hybrid weights
- Check existing code for precedents before planning:
  - `ai-server/src/` — existing service, retrieval, chain, router patterns
  - `ai-server/pyproject.toml` — current dependencies
  - `ai-server/configs/` — existing config file structure

## Steps — A. Plan

1. Output the implementation plan first. Do not write any code yet.
   - Layer order (lower layers first):
     Pydantic schemas → repository (Chroma / PostgreSQL) → service (RAG chain, query rewriting) → router → tests in the same commit as the code they test.
   - File layout follows `docs/ops/code-convention.md`: path `ai-server/src/<module>/`, imported as `from src.<module> import ...`.
   - For each commit, list: files to change, layer, commit message (`type(scope): summary` from `CONTRIBUTING.md` §1.3).
   - Cite grounds for each decision as `document > section`.
2. List the following as option tables only. Do not decide.
   - Retrieval parameter choices (τ threshold, top-k, hybrid α) not finalized in `configs/rag.yaml`
   - Prompt template wording not settled
   - Error handling paths not in the specification
3. If an ADR and a reference document differ on the same point, follow the ADR and list the conflict.
4. **LLMOps flag**: if any commit changes `configs/` files, Jinja2 prompt templates, or RAG query-rewriting logic, mark it in the plan table — a Before/After evaluation result against the eval set is required at PR time (`CONTRIBUTING.md` §9.5).
5. **Contract change**: if any commit requires changing `docs/specs/interfaces.md` or `docs/specs/api-spec.md`, stop planning and propose the change as a prerequisite Issue before proceeding.
6. For infra-adjacent commits (Dockerfile, `docker-compose.yml` for `ai-server`): note that env-var additions must also be reflected in `docs/ops/env-reference.md`.
7. Output the plan and wait for approval.

Human gate: user approves plan and settles all items under 결정 필요.

## Steps — B. Each commit

1. Change only the files listed in the plan for this commit. If an unlisted file must change, state why and wait for approval.
2. Run the pre-commit routine and show the full output:
   ```bash
   uv run ruff check src && uv run ruff format --check src
   uv run mypy src
   uv run pytest -q -m "not llm and not eval"
   ```
   Run locally only (never in CI):
   - LLM-call tests: `uv run pytest -m llm`
   - Full RAG eval (costs money): `uv run pytest -m eval`
3. Show `git diff --stat` and the commit message, then wait for approval.
4. Commit only after the user says to commit. Output the push command; do not run it.
5. **Prompt templates**: changes to prompt text go in `configs/prompts/` as Jinja2 `.j2` files only. No prompt strings in Python source.
6. **Config values**: τ thresholds and retrieval parameters belong in `configs/rag.yaml`, with `TAU_{SOURCE_KEY_UPPER}` env-var as fallback. Do not hardcode.
7. **Dependencies**: add via `uv add <package>` and commit `uv.lock` in the same commit (ADR-007 SHA pinning).
8. **Chroma collections**: follow per-source collection isolation (ADR-004). Do not query across collections.
9. If a change affects runtime behavior (Chroma, OpenAI API call, PostgreSQL connection, secret usage), recommend running verification in a separate terminal:
   > 비밀값이 필요한 명령은 Claude Code 터미널이 아닌 별도 터미널에서 직접 실행한다.
10. If a step fails, go to stage 60 (troubleshoot). Return here after the fix and continue with step B.

Human gate: review `git diff --stat` and commit message, then say to commit.

## Output format

```markdown
### 커밋 계획
| # | 레이어 | 파일 | 커밋 메시지 | LLMOps eval 필요 | 근거 |
| --- | --- | --- | --- | --- | --- |

### 결정 필요
| 판단 | 선택지 | 장점 | 단점 | 근거 문서 |
| --- | --- | --- | --- | --- |

### ADR과 기준 문서의 차이
-
```

## Do not

- Write code before the plan is approved.
- Change files outside the plan without approval.
- Use a response field, status code, or error shape not in `docs/specs/interfaces.md`.
- Hardcode prompt strings in Python source — use `configs/prompts/` Jinja2 templates.
- Hardcode τ thresholds or retrieval parameters — use `configs/rag.yaml`.
- Plan a `configs/` or RAG logic commit without flagging the eval requirement.
- Run `uv add` without committing `uv.lock` in the same commit.
- Run commands that need secret values in the Claude Code terminal.
- Commit while `ruff`, `mypy`, or unit tests fail.
- Push — output the push command for the user to run.

## Human gate

- Approve the plan; settle items under 결정 필요; create a prerequisite document Issue when a contract change is needed.
- Review `git diff --stat` and the commit message for each commit, then say to commit.
