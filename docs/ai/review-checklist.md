# 리뷰 체크리스트

자체 리뷰(`docs/ai/prompts/40-review.md`)와 사람 리뷰가 함께 쓰는 기준이다.  
각 항목은 대조할 대상과 근거 위치만 적는다. 판단 기준은 근거 문서에 있다.

## 판정

| 판정 | 의미 |
| --- | --- |
| 통과 | 근거(파일, 실행한 명령과 결과)를 함께 적는다. |
| 미통과 | 위치와 이유를 적는다. |
| 해당 없음 | 이유를 적는다. |
| 미확인 | 확인하지 못한 항목이다. 통과로 바꾸지 않는다. |

**적용 범위**

- **항상 적용**: A, H, K, N
- **코드 변경 시**: I, J
- **Java 코드 변경 시**: B, D, L
- **Python 코드 변경 시**: E, M
- **Backend API 계약 변경 시**: B
- **도메인 로직·정책 변경 시**: C
- **엔티티·저장소·Flyway 변경 시**: D
- **ai-server/ RAG 변경 시**: E
- **infra/ Docker Compose·nginx 변경 시**: F
- **frontend/ 변경 시**: G

---

## A. 범위

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| A1 | Issue 범위 밖 파일 변경이 없는가 | `git diff --stat develop...HEAD` | `AGENTS.md` > §3 Scope and prohibitions |
| A2 | 커밋 단위·제목이 규칙에 맞는가 | `git log --oneline develop..HEAD` | `CONTRIBUTING.md` > §2 커밋 규칙 |
| A3 | PR 크기가 300줄 이내인가, 넘는다면 쪼갤 수 없는 이유가 있는가 | `git diff --shortstat develop...HEAD` (lock 파일 제외) | `CONTRIBUTING.md` > §4.1 PR 규칙 |

---

## B. API 명세 (Backend REST API 변경 시)

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| B1 | 메서드·경로가 명세와 같은가 | Controller 매핑 ↔ 명세 | `docs/specs/api-spec.md` > 해당 엔드포인트 |
| B2 | 요청 필드·필수 여부·검증 조건이 명세와 같은가 | 요청 DTO ↔ 명세 | `docs/specs/api-spec.md` > 해당 API |
| B3 | 응답 필드·상태 코드가 명세와 같은가 | 응답 DTO ↔ 명세 | `docs/specs/api-spec.md` > 해당 API |
| B4 | Backend → AI Server 인터페이스가 명세와 같은가 | `client/` 호출 코드 ↔ 명세 | `docs/specs/interfaces.md` > 해당 호출 |
| B5 | 명세에 없는 필드·엔드포인트가 없는가 | diff | `docs/specs/api-spec.md` > 해당 섹션 |

---

## C. 도메인 정책·상태 (도메인 로직 변경 시)

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| C1 | 허용된 상태 전이만 있는가 | 상태 변경 코드 ↔ 전이 규칙 | `docs/planning/policy.md` > 해당 도메인 |
| C2 | 게스트 쿼터(`GUEST_QUOTA=5`)·일일 쿼터(`DAILY_QUOTA=100`) 값이 정책 문서와 같은가 | 상수·설정 ↔ 문서 | `docs/planning/policy.md`, `.env.example` |
| C3 | 미결정 사항에 걸린 로직을 임의로 정하지 않았는가 | 미결정 항목 목록 | `docs/planning/policy.md` > 미결정 사항 |
| C4 | 관련 ADR과 충돌하지 않는가 | ADR 목록 ↔ 코드 변경 | `docs/adr/` > 해당 ADR |

---

## D. 데이터·트랜잭션 (엔티티·저장소·Flyway 변경 시)

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| D1 | 엔티티·제약이 ERD와 같고 Flyway 마이그레이션(`V{n}__{desc}.sql`)이 있는가 | 엔티티 ↔ ERD ↔ `V*.sql` | `docs/specs/db-design.md` |
| D2 | `ddl-auto: validate` 환경에서 DDL을 `init.sql`에 직접 쓰지 않았는가 | `src/main/resources/` 확인 | `AGENTS.md` > §8 Architecture overview |
| D3 | `@Transactional` 위치가 올바른가 (서비스 public 메서드, 조회 `readOnly=true`) | 서비스 코드 | `docs/ops/code-convention.md` > §4 |
| D4 | `open-in-view: false` 환경에서 Lazy 로딩이 발생하지 않는가 | 서비스·컨트롤러 호출 흐름 | `docs/ops/code-convention.md` > §4 |

---

## E. RAG 파이프라인 (ai-server/ 변경 시)

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| E1 | τ 임계값 하드코딩이 없는가 (`configs/rag.yaml` 또는 `TAU_{SOURCE_KEY_UPPER}` env var 참조) | `grep -rn` 소스 검색 | ADR-008, `.env.example` |
| E2 | Chroma 컬렉션명 하드코딩이 없는가 | `grep -rn` 소스 검색 | ADR-004 |
| E3 | 소스 어댑터 패턴을 따르는가 (신규 소스 추가 시 어댑터 등록) | `src/ingest/` 변경 ↔ 어댑터 목록 | ADR-006 |
| E4 | 쿼리 재작성 로직 변경 시 평가 결과(Before/After)가 PR에 포함됐는가 | PR 본문 측정 결과 섹션 | ADR-009 |
| E5 | `configs/` 변경 시 Before/After 측정 결과가 PR에 포함됐는가 | PR 본문 측정 결과 섹션 | `CONTRIBUTING.md` > §9.5 LLMOps |
| E6 | 프롬프트 문자열이 코드에 하드코딩되지 않았는가 (`configs/prompts/` 관리) | `grep -rn` 소스 검색 | `CONTRIBUTING.md` > §9.5 LLMOps |
| E7 | RAG 평가 테스트에 `eval` 마커가 붙어 있는가 | 테스트 파일 | `ai-server/pyproject.toml` > markers |

---

## F. 인프라·배포 (infra/ 변경 시)

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| F1 | docker-compose.yml 변경 시 `docs/ops/deployment.md`에 반영됐는가 | diff ↔ 문서 | `docs/ops/deployment.md` |
| F2 | 환경 변수 추가·변경 시 `docs/ops/env-reference.md`와 `.env.example`에 반영됐는가 | diff ↔ 문서 ↔ `.env.example` | `docs/ops/env-reference.md` |
| F3 | nginx SSE 설정 (`proxy_buffering off`, `proxy_read_timeout 300s`)이 제거·변경되지 않았는가 | `infra/nginx/conf.d/default.conf` diff | ADR-003 |
| F4 | 서비스 간 의존 순서 (`depends_on: service_healthy`)가 유지됐는가 | docker-compose.yml diff | ADR-002 |

---

## G. 프론트엔드 (frontend/ 변경 시)

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| G1 | `frontend/AGENTS.md`가 존재한다면 먼저 읽었는가 | 파일 존재 여부 확인 | `AGENTS.md` > §8 Architecture overview |
| G2 | SSE 요청이 `fetch + ReadableStream`으로 구현됐는가 (`EventSource` 사용 금지) | `grep -rn "EventSource"` | ADR-003 |
| G3 | `npm run lint && npm run build`가 통과하는가 | 실행 결과 | `CONTRIBUTING.md` > §5.3 Frontend |
| G4 | API 호출이 `VITE_API_BASE_URL` env var을 사용하는가 (URL 하드코딩 없음) | `grep -rn "localhost:8080"` | `.env.example` |

---

## H. 보안·인증

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| H1 | 비밀값이 코드·설정·로그·테스트·문서에 없는가 | `git grep -nE "password=\|secret=\|sk-\|ghp_\|BEGIN .*PRIVATE"` | `AGENTS.md` > §0 Absolute rules |
| H2 | FastAPI 엔드포인트에 `X-Internal-Token` 검증 의존성이 있는가 | `src/api/` 의존성 주입 확인 | `AGENTS.md` > §8 Runtime topology |
| H3 | Spring Boot에서 JWT 만료·유효성 검증을 처리하는가 | Security 설정·필터 코드 | `docs/planning/policy.md` > 인증 정책 |
| H4 | 게스트 쿼터 우회가 불가한가 (`GUEST_QUOTA=5`) | 게스트 세션 카운터 로직 | `docs/planning/policy.md` > 게스트 정책 |
| H5 | `.env`, `.mcp.json` 경로가 커밋 메시지·코드 주석·이슈·PR에 없는가 | diff 텍스트 검색 | `AGENTS.md` > §3 Scope and prohibitions |

---

## I. 테스트 (코드 변경 시)

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| I1 | 신규 로직에 단위 테스트가 있는가 | 테스트 파일 목록 | `docs/experiments/evaluation.md` |
| I2 | 단위 테스트가 실제 LLM/DB 없이 실행되는가 (mock 사용) | `import unittest.mock` 확인 | `ai-server/pyproject.toml` > markers |
| I3 | LLM 호출 테스트에 `llm` 마커가 붙어 있는가 | 테스트 파일 | `ai-server/pyproject.toml` > markers |
| I4 | `uv run pytest -q` (CI 기준: `not llm and not eval`) 로컬 통과 | 실행 결과 | `ai-server/pyproject.toml` > addopts |

---

## J. 빌드 (코드 변경 시)

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| J1 | Java 변경 시 `./gradlew spotlessApply` → `compileJava` → `compileTestJava` 실행 | 실행 결과 | `AGENTS.md` > §7 Build & test commands |
| J2 | Python 변경 시 `uv run ruff check --fix .` → `uv run mypy src` 실행 | 실행 결과 | `AGENTS.md` > §7 Build & test commands |
| J3 | `pyproject.toml` 변경 시 `uv.lock`을 같은 커밋에 포함했는가 | `git diff --name-only` | `CONTRIBUTING.md` > §0.1 절대 원칙 |
| J4 | `frontend/package.json` 변경 시 `package-lock.json`을 같은 커밋에 포함했는가 | `git diff --name-only` | `CONTRIBUTING.md` > §0.1 절대 원칙 |

---

## K. 문서 반영

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| K1 | 계약 변경(API 명세, ERD, 에러 코드, 정책) 시 `docs/specs/` 문서 PR이 먼저 병합됐는가 | 관련 PR 목록 | `AGENTS.md` > §2 Document rules |
| K2 | 환경 변수 추가·변경 시 `docs/ops/env-reference.md` + `.env.example` 함께 반영됐는가 | diff 비교 | `docs/ops/env-reference.md` |
| K3 | ADR이 필요한 결정인가 (대안 2개 이상, 나중에 바꾸면 여러 모듈 수정 필요) | ADR 작성 조건 대조 | `CONTRIBUTING.md` > §9.4 ADR |
| K4 | 기준 문서 섹션명을 바꿨다면 `AGENTS.md`·프롬프트·이 체크리스트의 참조도 고쳤는가 | `grep -rn` 섹션명 검색 | `AGENTS.md` > §4 Reference documents |

---

## L. Java 코드 구조 (Java 코드 변경 시)

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| L1 | 패키지 위치가 기준과 같은가 (`com.r1nn.contextq.{domain}/controller, service, repository, domain, dto, client`) | 변경 파일 경로 | `AGENTS.md` > §8 Backend package layout |
| L2 | Controller 반환 타입이 `ResponseEntity<ApiResponse<T>>`인가 | Controller 반환 타입 | `AGENTS.md` > §8 Backend package layout |
| L3 | Service: public 메서드에만 `@Transactional`, 조회는 `readOnly=true`인가 | 서비스 어노테이션 | `docs/ops/code-convention.md` > §4 |
| L4 | Domain: `@Setter/@Builder` 없음, protected 기본 생성자, 정적 팩토리인가 | 엔티티 클래스 | `docs/ops/code-convention.md` > §4 |
| L5 | DTO: `record` 사용, 응답용 `static from(entity)` 패턴인가 | DTO 클래스 | `docs/ops/code-convention.md` > §4 |
| L6 | 외부 HTTP 호출이 `client/` 패키지에서 트랜잭션 밖에서 실행되는가 | 클라이언트 호출 위치 | `AGENTS.md` > §8 Backend package layout |
| L7 | 전역 설정이 `@ConfigurationProperties`를 사용하는가 (`@Value` 금지) | 설정 클래스 | `docs/ops/code-convention.md` > §4 |

---

## M. Python 코드 구조 (Python 코드 변경 시)

| # | 확인 | 방법 | 근거 |
| --- | --- | --- | --- |
| M1 | 모듈 위치가 `ai-server/src/<module>/`인가 (`ai-server/ai_server/` 아님) | 변경 파일 경로 | `AGENTS.md` > §8 AI Server package layout |
| M2 | import 경로가 `from src.<module> import ...`인가 (`from ai_server...` 아님) | import 문 | `AGENTS.md` > §8 AI Server package layout |
| M3 | 환경 변수 접근이 `src/config/settings.py` BaseSettings를 통해서만 이루어지는가 | `grep -rn "os.environ\|os.getenv"` | `ai-server/pyproject.toml` > pydantic-settings |
| M4 | mypy 검사 대상이 `src`인가 (`ai_server` 아님) | `uv run mypy src` 명령 | `AGENTS.md` > §7 Build & test commands |
| M5 | 프롬프트 문자열이 `configs/prompts/` Jinja2 템플릿으로 외부화됐는가 | `grep -rn` 소스 검색 | `CONTRIBUTING.md` > §9.5 LLMOps |

---

## N. 문서·AI 산출물

문서·설정·Issue·PR·주석·AI가 작성한 코드에 모두 적용한다.

| # | 확인 | 방법 |
| --- | --- | --- |
| N1 | 구현됐다고 쓴 내용을 PR 설명이 아니라 코드·설정에서 직접 확인했는가 | 해당 파일 열람 |
| N2 | 존재하지 않는 구성을 있는 것처럼 쓰지 않았는가 | 서술한 구성 요소의 파일·설정 위치 확인 |
| N3 | CI 동작을 설정 파일로 확인했는가 | `.github/workflows/` diff |
| N4 | 사람마다 다르게 구현할 수 있는 표현이 없는가 (예: "필요하면", "적절히") | 문장 검토 |
| N5 | 확인을 건너뛰어도 되는 것처럼 읽히는 문장이 없는가 | 문장 검토 |
| N6 | 한 문서·한 Issue에 한 주제만 있는가 | 목차·변경 범위 |
| N7 | 위치를 행 번호가 아니라 `문서 > 섹션 > 찾을 문구`로 적었는가 | 인용 표기 |
| N8 | 비밀값 대신 `<placeholder>`만 있는가 | H1 결과 재활용 |
| N9 | 모르는 값(Issue 번호·완료 기한)을 추측으로 채우지 않았는가 | 빈 자리 확인 |
| N10 | AI가 채운 날짜·번호·이름·버전을 실제 값과 대조했는가 | 달력·Issue·`pyproject.toml`·`build.gradle` |
