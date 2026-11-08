# ContextQ-RAG

> **공식 기술 문서 연계 LLM 기반 개발 학습 질의응답 플랫폼**

LangChain 공식 문서를 버전별로 색인하고, 사용자가 선택한 버전 범위 내에서만 검색하여 출처 URL과 함께 답변을 반환하는 RAG 기반 Q&A 서비스입니다.

---

## 주요 기능

| 기능 | 설명 |
| --- | --- |
| 버전 선택 RAG 검색 | v0.3 / v1.x 중 선택한 버전의 공식 문서에서만 검색 |
| 출처 URL 반환 | 답변 근거가 된 문서의 커밋 SHA 고정 permalink 제공 |
| SSE 스트리밍 | `meta(출처) → token* → done` 순서로 청크 단위 스트리밍 |
| NO_CONTEXT 처리 | 버전 범위 밖 질문은 LLM 미호출, 명시적 안내 반환 |
| 멀티턴 대화 | 대화 이력 기반 질의 재작성으로 연속 질문 지원 |
| 버전 비교 모드 | v0.3 / v1.x 답변을 나란히 비교 |
| JWT 인증 / 익명 세션 | 비로그인 5회 체험 → 로그인 후 일일 100회 |

---

## 기술 스택

| 계층 | 기술 |
| --- | --- |
| AI 서버 | Python 3.12, FastAPI, LangChain, Chroma, `text-embedding-3-small` |
| 백엔드 | Java 21, Spring Boot 3, PostgreSQL |
| 프론트엔드 | React, TypeScript, Vite |
| 인프라 | Docker Compose, EC2 t3.small |
| 패키지 관리 | uv (Python), Gradle (Java), npm (Node.js) |
| 로컬 훅 | lefthook (`pre-commit`, `commit-msg`, `pre-push`) |

---

## 로컬 실행

### 사전 준비

- Docker Desktop 설치
- `.env.example`을 복사해 `.env`를 만들고 값을 채운다.

```bash
cp .env.example .env
# .env 파일을 열어 OPENAI_API_KEY 등 필수 값 입력
```

### 전체 스택 기동

```bash
make up       # Docker Compose로 전체 스택 기동
make down     # 스택 종료
make logs     # 로그 확인
```

서비스 포트 (기본값):

| 서비스 | 포트 |
| --- | --- |
| AI 서버 (FastAPI) | `http://localhost:8000` |
| 백엔드 (Spring Boot) | `http://localhost:8080` |
| 프론트엔드 (Vite) | `http://localhost:5173` |

### 인덱스 빌드 (최초 1회)

Chroma 벡터 인덱스는 로컬에서 빌드 후 EC2에 전송합니다.
프로덕션 서버에서는 직접 빌드하지 않습니다.

```bash
make build-index   # 문서 수집 → 파싱 → 임베딩 → Chroma 저장
```

> 상세 절차는 `docs/ops/data-pipeline.md`를 참고합니다. (작성 예정)

### 개발 환경 (서비스별)

```bash
# AI 서버
cd ai-server
uv sync
uv run uvicorn src.main:app --reload

# 백엔드
cd backend
./gradlew bootRun

# 프론트엔드
cd frontend
npm install
npm run dev
```

---

## 테스트

```bash
make test                      # 전체 단위 테스트

# AI 서버 단독
cd ai-server
uv run pytest -q               # 단위 테스트 (LLM 호출 제외)
uv run pytest -m llm           # 실제 LLM 호출 테스트 (로컬)
uv run pytest -m eval          # RAG 평가 (평가셋 전체, 비용 발생)
```

---

## 프로젝트 구조

```
contextq-rag/
├── ai-server/          # FastAPI — RAG 체인, 검색, 인덱스 빌드
├── backend/            # Spring Boot — 사용자 인증, 대화 이력
├── frontend/           # React — Q&A UI, 비교 뷰
├── scripts/            # 오프라인 수집·실험 스크립트
├── configs/            # 프롬프트·모델·검색 설정 (YAML)
├── infra/              # Docker Compose
├── docs/               # 명세·ADR·운영 문서
├── CLAUDE.md           # Claude Code 진입점 → AGENTS.md
├── AGENTS.md           # AI 에이전트 운영 규칙
├── CONTRIBUTING.md     # Git/GitHub 협업 규칙
├── lefthook.yml        # pre-commit 훅
├── Makefile            # 단축 명령어
└── .env.example        # 환경 변수 키 목록
```

---

## 문서

| 문서 | 내용 |
| --- | --- |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 브랜치 전략, 커밋 규칙, PR 가이드 |
| [`AGENTS.md`](AGENTS.md) | AI 에이전트 작업 규칙 |
| `docs/specs/api.md` | REST API 명세 (작성 예정) |
| `docs/specs/erd.md` | DB 스키마 (작성 예정) |
| `docs/adr/` | 아키텍처 결정 기록 (작성 예정) |
| `docs/ops/data-pipeline.md` | 인덱스 빌드·배포 절차 (작성 예정) |

---

end.