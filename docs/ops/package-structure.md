# 패키지 구조 기준

> **최종 수정일:** 2026-11-17

---

## 1. 백엔드 패키지 구조

### 1.1 루트 패키지

```
backend/contextq/src/main/java/com/r1nn/contextq/
├── auth/          # 인증·JWT (Controller, Service, Filter)
├── chat/          # 질의 처리·이력 (Controller, Service, Repository)
├── domain/        # JPA Base 엔티티 공통 (createdAt, updatedAt)
├── infra/         # DB 설정, WebClient (ai-server 연동)
├── common/        # 예외 처리, 응답 DTO, 유틸리티
└── global/
    └── config/    # 앱 전역 설정 (Spring Security, @ConfigurationProperties)
```

> 현재 `ContextqApplication.java`와 `global/config/SecurityConfig.java`가 존재한다. 나머지 구조는 기능 구현 이슈에서 순차적으로 추가된다.

### 1.2 도메인별 레이어 구조

```
<domain>/
├── controller/    # @RestController — HTTP 요청·응답
├── service/       # @Service — 비즈니스 로직
├── repository/    # @Repository — JPA/JDBC 접근
├── dto/           # 요청·응답 DTO (record 권장)
└── domain/        # 도메인 엔티티·값 객체 (도메인 내부용)
```

> 모든 레이어를 반드시 갖출 필요는 없다. 단순 조회 API라면 controller + service만으로 충분.

### 1.3 도메인 간 의존 규칙

- **도메인 간 직접 참조 금지**: `auth.service`가 `chat.repository`를 직접 주입하지 않는다.
- 도메인 간 데이터 공유는 `common/`에 인터페이스 또는 공통 DTO를 정의한다.
- Spring Event를 사용한 느슨한 결합은 허용 (현재 MVP에서는 최소화).

### 1.4 각 도메인 역할

| 도메인 | 역할 |
|---|---|
| `auth` | 회원가입·로그인·로그아웃, JWT Access/Refresh 토큰 발급·검증, Spring Security 필터 |
| `chat` | 질의 요청·AI 서버 호출·SSE 중계, 대화 이력 저장·조회, 게스트 쿼터 관리 |
| `domain` | 여러 도메인에서 공통으로 사용하는 JPA Base 엔티티 |
| `infra` | DataSource 설정, Flyway, WebClient (ai-server 연동) |
| `common` | 글로벌 예외 핸들러, 표준 응답 래퍼 (`ApiResponse<T>`), 유틸리티 |
| `global` | `config/`: 도메인에 속하지 않는 앱 전역 설정 — Spring Security 필터 체인, `@ConfigurationProperties` 바인딩 |

### 1.5 신규 도메인 추가 절차

1. `docs/ops/package-structure.md` §1.4 테이블에 역할 추가
2. `docs/specs/db-design.md`에 관련 ERD 추가
3. `code-convention.md §5` 스코프 목록 업데이트 (신규 scope 필요 시)
4. `docs/ai/review-checklist.md §L` 업데이트

---

## 2. ai-server 모듈 구조

### 2.1 패키지 레이아웃

`pyproject.toml`의 `packages = ["src"]` 설정에 따라 패키지 루트는 `ai-server/src/`다.

```
ai-server/
├── src/                   # 패키지 루트 (packages = ["src"])
│   ├── adapters/          # Source Adapter — 버전별 문서 수집·정규화 (ADR-006)
│   ├── config/            # pydantic-settings — 비밀값 로드 (settings.py)
│   ├── domain/            # 도메인 모델·값 객체 (NormalizedDocument 등)
│   ├── ingest/            # 문서 파싱·청킹·Chroma 적재
│   ├── pipeline/          # RAG 체인·LLM 호출 (LangChain LCEL)
│   ├── routers/           # FastAPI 라우터·엔드포인트
│   └── main.py            # FastAPI 앱 엔트리포인트
├── configs/
│   └── prompts/           # Jinja2 프롬프트 템플릿 (*.j2)
├── tests/
│   ├── integration/
│   └── unit/
├── pyproject.toml
└── uv.lock                # 절대 .gitignore 금지 — 재현성 보장
```

### 2.2 임포트 규칙

```python
# ✅ 올바른 임포트
from src.config.settings import settings
from src.pipeline.chain import RagChain

# ❌ 잘못된 임포트
from ai_server.config.settings import settings
```

### 2.3 주요 명령어

```bash
# 타입 검사
uv run mypy src

# 테스트
cd ai-server && uv run pytest -q

# 린트·포맷
uv run ruff check --fix .
uv run ruff format .
```

---

## 3. 테스트 위치

| 서버 | 테스트 경로 |
|---|---|
| 백엔드 | `backend/contextq/src/test/java/com/r1nn/contextq/` |
| ai-server | `ai-server/tests/` |

> ai-server `tests/`는 `src/`와 같은 레벨에 위치한다.