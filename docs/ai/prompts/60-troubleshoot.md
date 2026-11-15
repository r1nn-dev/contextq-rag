# 60. Troubleshooting

## Purpose

Find the root cause of a build or test failure, or of a review comment, produce a fix
proposal, and record the finding in a structured troubleshooting entry.

## When to use

- When a local or CI build or test fails
- When a stage 40 `미통과` item requires investigation before fixing
- When a CI check on the PR fails
- When applying review comments that need investigation

## Inputs

- The full error message or the review comment (paste in full — do not summarize)
- Enough surrounding code for context (file path and line range)
- Reference documents and ADRs applicable to the failure area

## Steps

1. **Categorize the failure** by stack:

   | Stack | Common failure types |
   | --- | --- |
   | ai-server | `ruff` lint/format, `mypy` type error, `pytest` failure, `uv` dependency error, Chroma schema mismatch, OpenAI API error |
   | backend | Gradle build error, Flyway migration error, Spring Boot startup failure, `spotlessCheck` format violation, test failure |
   | frontend | TypeScript type error, ESLint error, Vite build error, `npm` dependency error |
   | infra | Docker Compose startup error, missing environment variable, port conflict |

2. Summarize the symptom in one line: `[stack] symptom in one sentence`.
3. List the possible causes from most to least likely, with a way to check each
   (command, log file location, or file path).
4. **Ask before running any check command.** After approval, run the commands and
   show the full output.
5. When the cause is confirmed, propose a fix.
   - **ADR conflict check**: before proposing, verify that the fix does not contradict any ADR
     in `docs/adr/`. If it does, report the conflict and stop — do not proceed without approval.
   - If the fix requires a change to `docs/specs/interfaces.md`, `docs/specs/api-spec.md`, or
     `docs/specs/db-design.md`, stop and propose a prerequisite document Issue first.
6. Write the fix commit message following `CONTRIBUTING.md` commit message conventions.
   Include the root cause in the subject line (e.g., `fix(ai-server): resolve mypy error — missing return type on ...`).
7. Apply fixes through stage 30 Step B — one commit at a time. Do not batch multiple fixes.
8. Output a structured troubleshooting record.

Human gate: the user approves running each check command and decides the fix.
Fixes are applied through stage 30 Step B with per-commit approval.

## Output format

```markdown
### 증상
[stack] 한 줄 요약

### 원인 후보
| 순위 | 후보 | 확인 방법 | 결과 |
| --- | --- | --- | --- |

### ADR 충돌 여부
(해당 없으면 "해당 없음")

### 수정 방안
- 대상 파일:
- 변경 내용:
- 커밋 메시지:
- 계약 변경 필요: 예 / 아니오

### 트러블슈팅 기록
- **증상**:
- **원인**:
- **해결**:
- **교훈**:
```

## Do not

- Propose a fix that hides the symptom without confirming the cause: disabling a test,
  ignoring an exception, or raising a timeout. If unavoidable, state the reason and propose
  a follow-up issue.
- Proceed with a fix that conflicts with an ADR without reporting it first.
- Apply fixes without stage 30 Step B approval (no batch fixes).
- Run check commands without asking first.
- Silence `mypy` errors with `# type: ignore` without documenting the reason.
- Hardcode secrets or configuration values as a temporary workaround.

## Human gate

- The user approves running each check command.
- The user decides the fix and it is applied through stage 30 Step B.
- For ADR conflicts or contract changes: the user decides the direction before any fix is made.
