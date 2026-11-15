# 30. Implement — backend

## Purpose

Implement a confirmed Issue scope in `backend/` one commit at a time, with approval before each commit.

## When to use

After the user approves the stage 00 report and the stage 10 commit plan.

## Inputs

- Issue number and settled scope from stages 00 and 10
- ADRs and reference documents identified in stage 00
- `docs/specs/api-spec.md` — REST endpoints, request/response schema, status codes
- `docs/specs/db-design.md` — table schema, relationships, Flyway migration notes
- `docs/specs/interfaces.md` — X-Internal-Token, ai-server proxy contract
- `docs/planning/policy.md` — business rules, state transitions, session limits
- `docs/ops/code-convention.md` — Java style, package structure
- Check existing code for precedents before planning:
  - `backend/src/main/java/` — existing domain, repository, service, controller patterns
  - `backend/build.gradle` — current dependencies (Spring Boot 4.x: `flyway-database-postgresql` is a separate dependency from `flyway-core`)
  - `backend/src/main/resources/db/migration/` — existing Flyway migrations

## Steps — A. Plan

1. Output the implementation plan first. Do not write any code yet.
   - Layer order (lower layers first):
     Domain entity → Repository → Service → Controller → tests in the same commit as the code they test.
   - Follow `docs/ops/code-convention.md` for package structure and naming conventions.
   - For each commit, list: files to change, layer, commit message (`type(scope): summary` from `CONTRIBUTING.md` §1.3).
   - Cite grounds for each decision as `document > section`.
2. List the following as option tables only. Do not decide.
   - Transaction boundary choices not settled in the specification
   - Exception handling paths not in `docs/specs/api-spec.md`
   - Values or behaviors not in the documents
3. If an ADR and a reference document differ on the same point, follow the ADR and list the conflict.
4. **Contract change**: if any commit requires changing `docs/specs/api-spec.md`, `docs/specs/db-design.md`, `docs/specs/interfaces.md`, or `docs/planning/policy.md`, stop planning and propose the change as a prerequisite Issue before proceeding.
5. For infra-adjacent commits (Dockerfile, `docker-compose.yml` for `backend`): note that env-var additions must also be reflected in `docs/ops/env-reference.md`.
6. Output the plan and wait for approval.

Human gate: user approves plan and settles all items under 결정 필요.

## Steps — B. Each commit

1. Change only the files listed in the plan for this commit. If an unlisted file must change, state why and wait for approval.
2. Run the pre-commit routine and show the full output:
   ```bash
   ./gradlew spotlessApply
   ./gradlew build -x test
   ./gradlew test
   ```
3. Show `git diff --stat` and the commit message, then wait for approval.
4. Commit only after the user says to commit. Output the push command; do not run it.
5. **DB schema changes**: create a Flyway migration in `backend/src/main/resources/db/migration/` following the `V{n}__{description}.sql` naming convention. Do not run DDL directly against the database.
6. **X-Internal-Token**: set via environment variable; never hardcode. When proxying to ai-server, forward the token per `docs/specs/interfaces.md`.
7. If a change affects runtime behavior (Spring Security filter chain, DB connection, ai-server proxy, secret handling), recommend running verification in a separate terminal:
   > 비밀값이 필요한 명령은 Claude Code 터미널이 아닌 별도 터미널에서 직접 실행한다.
8. If a step fails, go to stage 60 (troubleshoot). Return here after the fix and continue with step B.

Human gate: review `git diff --stat` and commit message, then say to commit.

## Output format

```markdown
### 커밋 계획
| # | 레이어 | 파일 | 커밋 메시지 | 근거 |
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
- Use a response format, status code, or error code not in `docs/specs/api-spec.md`.
- Hardcode the X-Internal-Token value.
- Run DDL directly — use Flyway migrations in `backend/src/main/resources/db/migration/`.
- Run commands that need secret values in the Claude Code terminal.
- Commit while compilation or tests fail.
- Push — output the push command for the user to run.

## Human gate

- Approve the plan; settle items under 결정 필요; create a prerequisite document Issue when a contract change is needed.
- Review `git diff --stat` and the commit message for each commit, then say to commit.
