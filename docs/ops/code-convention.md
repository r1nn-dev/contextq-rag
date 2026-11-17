# 코드 컨벤션

> **최종 수정일:** 2026-11-17

---

## 1. 코드 스타일

### 1.1 Java — Spotless + googleJavaFormat

| 항목 | 값 |
|---|---|
| 포매터 | `googleJavaFormat('1.24.0')` |
| 임포트 정리 | `removeUnusedImports()` 자동 적용 |
| Spotless 버전 | `6.25.0` |
| SSOT | `backend/contextq/build.gradle` → `spotless.java.googleJavaFormat()` |

**원칙:** Spotless가 유일한 포맷 권위(SSOT)다. IntelliJ의 `Reformat Code`는 Spotless 설정과 충돌하므로 Java 파일에 대해서는 비활성화를 권장한다.

```gradle
// backend/contextq/build.gradle (스니펫)
plugins {
    id 'com.diffplug.spotless' version '6.25.0'
}

spotless {
    java {
        googleJavaFormat('1.24.0')
        removeUnusedImports()
    }
}
```

### 1.2 Python — Ruff

| 항목 | 값 |
|---|---|
| 포맷터 | `ruff format` |
| 린터 | `ruff check` |
| 최대 줄 길이 | `100`자 |
| 활성 rules | `E` (pycodestyle) · `F` (Pyflakes) · `I` (isort) · `UP` (pyupgrade) |
| 설정 파일 | `ai-server/pyproject.toml` → `[tool.ruff]` |

```toml
# ai-server/pyproject.toml (스니펫)
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
ignore = []
```

### 1.3 TypeScript / JavaScript — ESLint + Prettier

> **프론트엔드 AI 위임 영역.** `frontend/.eslintrc.*` 및 `frontend/.prettierrc` 기준. 직접 수정하지 않는다.

---

## 2. IDE 설정

### 2.1 IntelliJ IDEA (백엔드 개발)

1. **포맷 설정**: Java 포맷은 Spotless에 완전 위임. IntelliJ의 Reformat Code(Ctrl+Alt+L)는 사용하지 않는다.
2. **설정 파일 경로**: `backend/contextq/config/`
   - `.editorconfig` — 들여쓰기·인코딩 공통 설정
3. **권장 설정**:
   - Settings → Editor → Code Style → Java → Scheme: 프로젝트 기준
   - "Reformat on Save" 비활성화 (Spotless와 충돌 방지)

> ⚠️ IntelliJ의 Naver·Google 포매터 플러그인도 Spotless와 충돌한다. 플러그인 자동 포맷은 비활성화하고 `./gradlew spotlessApply`만 사용한다.

### 2.2 VSCode (Python·문서 편집)

- **Python**: [Ruff Extension](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff) 설치
- **Python 타입**: `ms-python.mypy-type-checker` 설치
- **Java**: Language Support for Java — 편집용 (포맷은 Spotless에 위임)
- **Markdown·YAML**: 기본 내장 지원

---

## 3. 빌드·린트 명령어

### 3.1 백엔드 (`backend/contextq`)

```bash
# 작업 중 (반복)
cd backend/contextq
./gradlew spotlessApply           # Java 포맷 적용 (커밋 전 필수)

# 커밋 전 최종 확인
./gradlew spotlessCheck           # CI에서 실행되는 검사
./gradlew compileJava             # 컴파일 확인
./gradlew compileTestJava         # 테스트 코드 컴파일
./gradlew clean test              # 전체 테스트
```

> **주의:** `./gradlew` 명령은 `backend/contextq/` 디렉터리에서 실행한다. 저장소 루트에서 직접 실행하면 Gradle wrapper를 찾지 못한다.

### 3.2 ai-server (`ai-server/`)

```bash
# 작업 중 (반복)
cd ai-server
uv run ruff check --fix .         # 린트 자동 수정
uv run ruff format .              # 포맷 적용

# 커밋 전 최종 확인
uv run mypy src                   # 타입 검사 (패키지 루트: src/)
uv run pytest -q                  # 단위 테스트 (llm·eval 마커 제외)
```

> **레이아웃 주의:** ai-server의 Python 패키지 루트는 `ai-server/src/`다 (`packages = ["src"]`).  
> `uv run mypy src`로 실행한다. `uv run mypy ai_server`는 경로 오류.

```bash
# 테스트 마커별 실행
uv run pytest -m llm              # LLM 실제 호출 테스트 (로컬만, CI 제외)
uv run pytest -m eval -q          # RAG 평가셋 전체 (OpenAI 비용 발생)
```

### 3.3 docs·CI 전용 작업 (Java·Python 변경 없음)

```bash
# docs-only 커밋 — spotlessApply 불필요
git add docs/
git commit -m "chore(docs): ..."
# CI spotlessCheck: Java 파일 미변경이므로 자동 통과
```

---

## 4. 패키지 구조

### 4.1 백엔드

```
backend/contextq/src/main/java/com/r1nn/contextq/
├── auth/          # 인증·JWT (Controller, Service, Filter)
├── chat/          # 질의 처리·이력 (Controller, Service, Repository)
├── domain/        # JPA 엔티티 공통
├── infra/         # DB 설정, WebClient (ai-server 연동)
├── common/        # 예외 처리, 응답 DTO, 유틸리티
└── global/config/ # 앱 전역 설정 (Spring Security, @ConfigurationProperties)
```

- 신규 도메인은 위 목록에 없는 경우 먼저 `docs/ops/package-structure.md`에 반영한다.
- 도메인 간 직접 참조 금지 — `common/` 또는 별도 인터페이스로 분리한다.

### 4.2 ai-server

```
ai-server/
├── src/                 ← Python 패키지 루트 (packages = ["src"])
│   ├── main.py          ← FastAPI 앱 엔트리포인트
│   ├── config/          ← pydantic-settings
│   ├── rag/             ← RAG 체인 (LangChain LCEL)
│   ├── retrieval/       ← Chroma 벡터 검색
│   ├── ingest/          ← 문서 수집·파싱·청킹
│   └── api/             ← FastAPI 라우터
├── configs/
│   └── prompts/         ← Jinja2 프롬프트 템플릿 (*.j2)
├── tests/
├── pyproject.toml
└── uv.lock              ← 절대 .gitignore 금지
```

> **임포트 규칙:**
> ```python
> # ✅ 올바른 임포트
> from src.config.settings import settings
>
> # ❌ 잘못된 임포트
> from ai_server.config.settings import settings
> ```

---

## 5. CI 잡

| 잡 이름 | 주요 단계 |
|---|---|
| `backend` | `spotlessCheck` → `compileJava` → `test` |
| `rag` | `ruff check` → `mypy src` → `pytest -m "not llm and not eval"` |
| `frontend` | ESLint → build |
| `pr-lint` | PR 제목 `type(scope):` 형식 검사 |

---

## 6. 의존성 주의 (Spring Boot 4.1.2)

### Flyway

Spring Boot 4.1.2에서 Flyway를 사용할 때 `spring-boot-starter-flyway`만으로는 PostgreSQL 드라이버를 찾지 못한다. 두 의존성을 **반드시 함께** 선언한다.

```gradle
// backend/contextq/build.gradle
dependencies {
    // Flyway: starter + flyway-database-postgresql 함께 필요
    implementation 'org.springframework.boot:spring-boot-starter-flyway'
    implementation 'org.flywaydb:flyway-database-postgresql'
}
```

### 테스트 의존성

Spring Boot 4.x는 모듈별 전용 테스트 스타터를 사용한다. Boot 3.x의 `org.testcontainers:postgresql` 패턴과 다르다.

```gradle
testImplementation 'org.springframework.boot:spring-boot-starter-webflux-test'
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
testImplementation 'org.testcontainers:testcontainers-postgresql'
```

---

## 7. pyproject.toml — pytest 마커

LLM 호출 및 RAG 평가 테스트는 CI에서 돌지 않는다. 아래 설정으로 기본 실행에서 제외된다.

```toml
# ai-server/pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "llm: LLM 실제 호출 (로컬 실행만, 비용 발생)",
    "eval: RAG 평가셋 전체 실행 (비용 발생)"
]
```

> CI에서 `uv run pytest -q` 를 실행하면 llm·eval 마커 테스트는 자동 제외된다.  
> 로컬에서 LLM 테스트 실행: `uv run pytest -m llm`  
> 평가셋 전체 실행: `uv run pytest -m eval -q` (OpenAI API 비용 발생 주의)
