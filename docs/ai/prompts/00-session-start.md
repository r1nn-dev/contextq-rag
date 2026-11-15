# 00. Session Start

## Purpose

Load the work context — Issue, branch, related ADRs, and reference documents — before any implementation begins. The report makes the scope, constraints, and open decisions explicit so the session starts from a verified base.

## When to use

- At the start of every AI session
- When switching to a different Issue within the same session

## Inputs

- `AGENTS.md` (re-read §1, §4, §6 at session start)
- Issue body — the user pastes it, or shares the Issue URL/number
- Output of `git branch --show-current` and `git status`

## Steps

Report only. Do not write code, create files, or change branches in this stage.

1. Re-read `AGENTS.md` §1 Before Starting Work and follow its checklist in order.
2. Summarize the Issue: purpose, scope, expected commit breakdown, and due date.
   Mark any value not stated in the Issue as blank — do not guess.
3. Run `git branch --show-current` and `git status`.
   Check whether the branch name follows `CONTRIBUTING.md` §1.3 Branch strategy.
4. List the ADRs in `docs/adr/` that constrain this work. Read the full text of each one you list.
5. From `AGENTS.md` §4 Reference documents, identify which documents and sections to read before implementing.
   Use the table below as a starting point; always cross-check with the actual Issue scope:

   | Change area | Documents to read |
   | --- | --- |
   | RAG / ai-server (retrieval, ingest, rag) | `docs/specs/rag-pipeline.md`, `docs/specs/interfaces.md`, ADR-002–009 |
   | Backend / Java (backend, api, auth) | `docs/specs/api-spec.md`, `docs/specs/db-design.md`, `docs/ops/code-convention.md` |
   | Config / prompt / eval (configs, eval) | `CONTRIBUTING.md` §9.5 LLMOps, `docs/experiments/evaluation.md` |
   | Infra / Docker (infra, ci, deps) | `docs/ops/deployment.md`, `docs/ops/env-reference.md` |
   | Frontend (frontend) | `frontend/AGENTS.md` (if present), `docs/specs/api-spec.md` |
   | Shared types / interfaces (shared) | `docs/specs/interfaces.md` |

6. If an ADR and a reference document conflict on the same point, list each difference as
   `document > section > phrase`. Follow the latest ADR and report the conflict.
7. List scope items that have no grounds in any document as questions.

## Output format

### 작업 준비 보고

| 항목 | 확인 결과 |
| --- | --- |
| Issue | 제목, 완료 기한 (없으면 "비어 있음") |
| 브랜치 | 이름, 규칙 일치 여부 |
| 관련 ADR | 파일명 (없으면 "없음") |
| 읽을 기준 문서 | 문서 > 섹션 |
| 미확인 항목 | — |

### ADR과 기준 문서의 차이

- 없음 / `문서 > 섹션 > 찾을 문구`: 차이 내용

### 확인이 필요한 항목

1.

## Do not

- Guess Issue scope, due date, or commit breakdown.
- Create or switch branches without user approval — propose the command and wait.
- Start implementing before the user reviews this report and says to proceed.
- Reference `.env` or `.mcp.json` paths in the report.

## Human gate

- The user reviews the 작업 준비 보고 and says to proceed.
- The user answers items under 확인이 필요한 항목, or confirms they are out of scope, before any work begins.
