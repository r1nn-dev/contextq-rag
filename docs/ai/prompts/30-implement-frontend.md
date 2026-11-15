# 30. Implement — frontend

## Purpose

Implement a confirmed Issue scope in `frontend/` one commit at a time, with approval before each commit. The frontend is AI-delegated — this prompt is the primary implementation driver for `frontend/`.

## When to use

After the user approves the stage 00 report and the stage 10 commit plan.

## Inputs

- Issue number and settled scope from stages 00 and 10
- ADRs and reference documents identified in stage 00
- `docs/specs/api-spec.md` — REST endpoints, request/response schema, status codes
- `docs/ops/code-convention.md` — TypeScript/React style, file naming conventions
- Check existing code for precedents before planning:
  - `frontend/src/` — existing component, hook, and API client patterns
  - `frontend/package.json` — current dependencies

## Steps — A. Plan

1. Output the implementation plan first. Do not write any code yet.
   - Commit order: shared types and API client wrappers → hooks / state → UI components → tests in the same commit as the code they test.
   - For each commit, list: files to change, component type (stateful / presentational), and commit message (`type(scope): summary` from `CONTRIBUTING.md` §1.3).
   - Cite grounds for each decision as `document > section`.
2. List the following as option tables only. Do not decide.
   - Component decomposition not settled by the specification
   - State management approach (URL state, context, local state)
   - UI behaviors or values not in the documents
3. If an ADR and a reference document differ on the same point, follow the ADR and list the conflict.
4. **SSE streaming**: chat responses are streamed via `fetch + ReadableStream`. Do NOT use `EventSource` — EventSource cannot send the `Authorization` header (ADR-003).
5. **Contract change**: if any commit requires a new endpoint or a type change in `docs/specs/api-spec.md`, stop planning and propose the change as a prerequisite Issue before proceeding.
6. Output the plan and wait for approval.

Human gate: user approves plan and settles all items under 결정 필요.

## Steps — B. Each commit

1. Change only the files listed in the plan for this commit. If an unlisted file must change, state why and wait for approval.
2. Run the pre-commit routine and show the full output:
   ```bash
   npm run lint
   npm run build
   ```
3. Show `git diff --stat` and the commit message, then wait for approval.
4. Commit only after the user says to commit. Output the push command; do not run it.
5. Before committing, verify:
   - API base path comes from an environment variable (`VITE_API_BASE_URL` or equivalent) — no hardcoded host or port.
   - `VITE_PUBLIC_` variables contain no secrets.
   - No `any` types — use `unknown` and narrow with type guards.
   - No inline `style={{}}` where a utility class applies.
   - No new package installed without explanation and approval.
6. If a step fails, go to stage 60 (troubleshoot). Return here after the fix and continue with step B.

Human gate: review `git diff --stat` and commit message, then say to commit.

## Output format

```markdown
### 커밋 계획
| # | 구분 | 파일 | 커밋 메시지 | 근거 |
| --- | --- | --- | --- | --- |

### 결정 필요
| 판단 | 선택지 | 장점 | 단점 | 근거 문서 |
| --- | --- | --- | --- | --- |

### ADR과 기준 문서의 차이
-
```

## Do not

- Write code before the plan is approved.
- Change files outside the plan without approval.
- Use `EventSource` for SSE — use `fetch + ReadableStream` (ADR-003).
- Hardcode API host or port — use environment variables.
- Use `any` — use `unknown` with a type guard.
- Put secrets in `VITE_PUBLIC_` variables.
- Install a new package without explaining why and getting approval.
- Commit while `npm run lint` or `npm run build` fails.
- Push — output the push command for the user to run.

## Human gate

- Approve the plan; settle items under 결정 필요; create a prerequisite document Issue when a contract change is needed.
- Review `git diff --stat` and the commit message for each commit, then say to commit.
