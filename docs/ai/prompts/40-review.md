# 40. Review

## Purpose

Check the author's own changes against `docs/ai/review-checklist.md` before creating a PR.
People make all decisions.

## When to use

After all commits of stage 30, before creating the PR.

## Inputs

- `git diff develop...HEAD` and `git diff --stat develop...HEAD`
- `docs/ai/review-checklist.md` and the documents each item points to
- The stage 30 commit plan (to confirm scope is complete)

## Steps

1. Run `git diff --stat develop...HEAD` and select the checklist sections that apply.
   Always include sections A (scope), H (security), K (docs), and N (AI output).
2. Open the reference document for each selected item and judge it as one of:
   `통과`, `미통과`, `해당 없음`, `미확인`.
   For `통과`, record the file and line number, or the command run and its result.
   For `미확인`, record why the command could not be run.
3. Run the pre-commit check commands for each stack present in the diff and show the full output:

   **ai-server** (when `ai-server/` is in the diff):
   ```bash
   uv run ruff check src && uv run ruff format --check src
   uv run mypy src
   uv run pytest -q -m "not llm and not eval"
   ```

   **backend** (when `backend/` is in the diff):
   ```bash
   ./gradlew spotlessCheck
   ./gradlew build -x test
   ./gradlew test
   ```

   **frontend** (when `frontend/` is in the diff):
   ```bash
   npm run lint
   npm run build
   ```

   **docs / configs only** (no source code change): no build check required; skip to step 4.

4. **LLMOps check**: if the diff includes any of the following, Before/After evaluation against
   the eval set is required at PR time (`CONTRIBUTING.md` §9.5). Mark as `미통과` if the eval
   results are not ready.
   - `configs/rag.yaml` or any other file under `configs/`
   - Jinja2 prompt templates (`configs/prompts/*.j2`)
   - RAG query-rewriting logic in `ai-server/src/`

5. For `미통과` items, propose a fix only. Do not make any changes.
6. Output the result and wait for approval.

Human gate: the author decides how to fix each `미통과` item and applies fixes through
stage 30 Step B. Do not create the PR until there are no `미통과` items.

## Output format

```markdown
### 적용 섹션
| 섹션 | 적용 여부 | 이유 |
| --- | --- | --- |

### 판정
| # | 섹션 | 항목 | 판정 | 근거 |
| --- | --- | --- | --- | --- |

### 실행한 명령
| 스택 | 명령 | 결과 |
| --- | --- | --- |

### LLMOps 체크
eval 필요 여부 및 근거 (해당 없으면 "해당 없음")

### 수정 필요
| # | 위치 | 수정 방안 |
| --- | --- | --- |
```

## Do not

- Mark a command you did not run as `통과`.
- Fix `미통과` items without approval — propose only.
- Skip the LLMOps check when `configs/` or RAG logic is in the diff.
- Create the PR while any item is `미통과`.
- Run `pytest -m llm` or `pytest -m eval` as part of the standard check — these are local-only
  and cost money; run them only when specifically testing LLM or RAG evaluation.

## Human gate

The author reviews the output, decides how to fix each `미통과` item, and applies fixes
through stage 30 Step B.
Do not create the PR until all items are `통과` or `해당 없음`.
