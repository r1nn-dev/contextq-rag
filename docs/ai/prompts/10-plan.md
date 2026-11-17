# 10. Plan

## Purpose

Break a feature, milestone, or task into concrete Issues and commit units. Flag open decisions, LLMOps requirements, and prerequisite document changes before coding begins.

## When to use

- **Step A**: before every new Issue, to verify ADR and document state
- **Step B**: at the start of a milestone or when scope changes, to plan Issues
- **Step C**: once per approved Issue, to plan commit units

## Inputs

- `docs/planning/planning.md` > `2. 작업 구성`, `3. 요구사항 명세`
- `CONTRIBUTING.md` §1.3 Branch strategy, §9.4 ADR, §9.5 LLMOps
- Milestone name and expected due date (from the user)
- Stack-relevant reference documents from `AGENTS.md` §4

## Step A — ADR and document check (before every Issue)

1. List the ADRs in `docs/adr/` that the upcoming work might be affected by.
2. For each ADR, confirm whether the direction is still valid or has known conflicts with the current codebase.
3. Identify reference document sections most relevant to this Issue (from `AGENTS.md` §4).
4. Report conflicts: if an ADR and a reference document differ on the same point, list
   `document > section > phrase` for each side. Follow the latest ADR.

Human gate: user confirms ADR state before Issue planning proceeds.

## Step B — Issue plan (milestone or scope change)

1. List features and priorities from `docs/planning/planning.md` > `3. 요구사항 명세`.
2. Group into Issues. Each Issue maps to one branch and one PR (`CONTRIBUTING.md` §1.3).
   An Issue that is too large to review in one PR must be split.
3. For each Issue, identify prerequisites:
   - Earlier Issues in the same domain it depends on.
   - Cross-domain dependencies:
     - Backend ↔ AI Server: `docs/specs/interfaces.md` (X-Internal-Token, request/response schema)
     - Frontend ↔ Backend API: `docs/specs/api-spec.md` (endpoint path, request, response)
   - Document-change Issues that must merge first (API spec, ERD, policy, ADR, interface spec).
4. Flag LLMOps requirements: if the Issue changes `configs/` files or RAG query-rewriting logic,
   a Before/After evaluation result against the eval set is required at PR time (`CONTRIBUTING.md` §9.5).
5. Put contracts that other Issues wait for (interface specs, API spec changes, ADRs) first in priority order.
6. Give grounds for each row as `document > section`.
7. Output the plan and wait for approval.

Human gate: user approves the Issue list and dependency order before commit planning.

## Step C — Commit unit plan (per Issue)

1. Split the Issue into commits by `CONTRIBUTING.md` §1.3. Each commit must pass build and tests
   independently before the next commit starts.
2. For each commit, state:
   - Title in `type(scope): summary` format (scope from `CONTRIBUTING.md` §1.3 scope table only)
   - Files to change (list)
   - Build routine needed: `spotlessApply` (Java), `ruff check + mypy src` (Python), or none (docs-only)
3. For each commit, identify what is settled vs what needs a decision:
   - Is the API path, request/response schema, and status code in `docs/specs/api-spec.md`?
   - Is the state transition in `docs/planning/policy.md`?
   - Is the DB schema in `docs/architecture/db-design.md`?
   - Is the AI Server ↔ Backend interface in `docs/specs/interfaces.md`?
   - Does this RAG/config change need a new ADR? (`CONTRIBUTING.md` §9.4)
   - Does this `configs/` or prompt change need Before/After eval results? (`CONTRIBUTING.md` §9.5)
4. If a commit requires a contract change first (API spec, ERD, policy, ADR, interface spec),
   create a separate `docs(docs):` or `chore(docs):` commit/Issue and make it a prerequisite.
5. Cite grounds as `document > section > phrase`.
6. Output the plan and wait for approval.

Human gate: user approves the commit unit breakdown and settles open decisions before implementation.

## Output format

**Step B:**

| # | Issue 제목 | scope | 선행 Issue | 의존 도메인 | LLMOps 필요 | 근거 |
| --- | --- | --- | --- | --- | --- | --- |

### 일정 위험
-

### 결정 필요
-

**Step C:**

### 문서 선행 커밋 · Issue

| # | 제목 | 바꿀 문서 > 섹션 | 이유 |
| --- | --- | --- | --- |

### 커밋 단위

| # | 커밋 제목 | 변경 파일 | 빌드 루틴 |
| --- | --- | --- | --- |

### 확정 사항

| 커밋 | 항목 | 내용 | 근거 |
| --- | --- | --- | --- |

### 결정 필요 사항

| 커밋 | 종류 | 질문 | 선택지 | 관련 ADR/문서 |
| --- | --- | --- | --- | --- |

## Do not

- Add features not in `docs/planning/planning.md`.
- Guess due dates or Issue numbers.
- Mark an open decision as settled.
- Plan a `configs/` or RAG logic commit without noting the eval requirement.
- Propose a scope name not in `CONTRIBUTING.md` §1.3 scope table.
- Plan a commit that changes `docs/specs/interfaces.md` as part of an implementation commit —
  contract changes get their own preceding commit or Issue.

## Human gate

- Step A: user confirms ADR state before Issue planning.
- Step B: user approves Issue list and dependency order.
- Step C: user approves commit units and settles open decisions before coding begins.
