# 환경 변수 레퍼런스

> **최종 수정일:** 2026-11-17

`.env`의 모든 변수와 GitHub Actions Secrets에 대한 설명, 생성 방법, 기본값을 정리한다.

---

## 1. 로컬 개발 환경 변수 (`.env`)

```bash
cp .env.example .env
# .env 를 편집하여 아래 필수 값을 채운다
```

### 1.1 PostgreSQL

| 변수명 | 설명 | 예시 / 기본값 | 필수 |
|---|---|---|---|
| `POSTGRES_DB` | 데이터베이스 이름 | `contextq` | ✅ |
| `POSTGRES_USER` | 사용자 이름 | `contextq_user` | ✅ |
| `POSTGRES_PASSWORD` | 비밀번호 | `openssl rand -hex 16` 출력값 | ✅ |
| `POSTGRES_HOST` | 호스트 | 로컬: `localhost` / Docker: `postgres` | ✅ |
| `POSTGRES_PORT` | 포트 | `5432` | ✅ |

```bash
# 비밀번호 생성
openssl rand -hex 16
```

> **Docker Compose 주의:** `postgres` 서비스 컨테이너 이름을 `POSTGRES_HOST`로 사용할 때는 `postgres`로 설정한다.  
> **ai-server**는 같은 `POSTGRES_*` 값으로 SQLAlchemy·Alembic 접속 URL을 만든다 (`ai` 스키마).  
> **운영 환경**은 `POSTGRES_*` 대신 `DB_URL` · `DB_USERNAME` · `DB_PASSWORD`를 사용한다 (§2 GitHub Secrets 참고).

### 1.2 OpenAI

| 변수명 | 설명 | 생성 방법 | 필수 |
|---|---|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 | [platform.openai.com](https://platform.openai.com) | ✅ |

> `sk-` 로 시작하는 값. 절대 저장소에 커밋하지 않는다.

### 1.3 JWT

| 변수명 | 설명 | 예시 / 기본값 | 필수 |
|---|---|---|---|
| `JWT_SECRET` | JWT 서명 키 (HS256) | `openssl rand -hex 32` 출력값 | ✅ |

```bash
# JWT 서명 키 생성
openssl rand -hex 32
```

> Access Token 만료 시간(`expiration-ms`)은 `application.yml`에 `86400000` (24시간)으로 고정 관리된다. `.env` 오버라이드 불필요.

### 1.4 Chroma (임베디드)

| 변수명 | 설명 | 예시 / 기본값 | 필수 |
|---|---|---|---|
| `CHROMA_DATA_DIR` | Chroma 데이터 저장 경로 | `./data/chroma` | ✅ |

> **Chroma는 ai-server에 임베디드**된다 (ADR-002). 별도 컨테이너나 `CHROMA_PORT` 환경 변수는 사용하지 않는다.  
> Colab 환경에서는 절대 경로로 설정한다: `/content/contextq-rag/data/chroma`

### 1.5 서비스 간 내부 인증

| 변수명 | 설명 | 생성 방법 | 필수 |
|---|---|---|---|
| `INTERNAL_TOKEN` | Spring Boot ↔ FastAPI 내부 인증 토큰 | `openssl rand -hex 32` 출력값 | ✅ |

```bash
# 내부 토큰 생성
openssl rand -hex 32
```

> Spring Boot가 FastAPI로 요청 시 `X-Internal-Token` 헤더에 이 값을 포함한다 (ADR-012).  
> 외부에 노출되면 RAG 파이프라인 직접 호출이 가능하므로 충분한 엔트로피 확보.

### 1.6 AI 서버 연동

| 변수명 | 설명 | 예시 / 기본값 | 필수 |
|---|---|---|---|
| `AI_SERVER_INTERNAL_URL` | Spring Boot → FastAPI 내부 URL | `http://localhost:8000` | 선택 |

> 미설정 시 `application.yml` 기본값 `http://localhost:8000`이 적용된다.  
> Docker Compose 환경에서는 컨테이너 이름으로 설정한다: `http://ai-server:8000`

### 1.7 프론트엔드

| 변수명 | 설명 | 예시 / 기본값 | 필수 |
|---|---|---|---|
| `VITE_API_BASE_URL` | 프론트엔드 API 호출 경로 접두사 | 빈 값 (동일 출처) | 선택 |

> Vite 환경 변수는 `VITE_` 접두사가 붙어야 브라우저 번들에 포함된다.  
> backend는 CORS를 허용하지 않는다(`docs/planning/policy.md` > §11 > "CORS 미허용"). 브라우저는 동일 출처의 `/api/...`를 호출하고, 개발 환경은 Vite 프록시, 운영은 nginx가 backend로 전달한다. 다른 출처 URL을 넣으면 요청이 차단된다.

### 1.8 애플리케이션 환경

| 변수명 | 설명 | 예시 / 기본값 | 필수 |
|---|---|---|---|
| `SPRING_PROFILES_ACTIVE` | Spring Boot 활성 프로파일 | `local` / `production` | 선택 |

### 1.9 ai-server 실행 프로필

| 변수명 | 설명 | 예시 / 기본값 | 필수 |
|---|---|---|---|
| `APP_PROFILE` | ai-server 실행 프로필. `local` · `staging` · `loadtest` · `prod` 중 하나 | `local` | 선택 |
| `INGEST_ENABLED` | 수집·임베딩 경로 활성화 | `false` | 선택 |
| `LLM_MOCK` | 생성 단계를 고정 토큰으로 대체하는 mock LLM | `false` | 선택 |

> `APP_PROFILE=prod`에서 `INGEST_ENABLED` 또는 `LLM_MOCK`이 `true`이면 ai-server가 기동하지 않는다 (`docs/planning/policy.md` > §2.2 불변식 > INV-17).  
> `APP_PROFILE=prod`에서는 FastAPI `/docs`를 노출하지 않는다 (`docs/planning/policy.md` > §9.1).

---

## 2. GitHub Actions Secrets

> Settings → Secrets and variables → Actions → New repository secret

| Secret 이름 | 설명 | 비고 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 | CI에서 LLM 테스트 불필요 → 현재는 미사용 |
| `JWT_SECRET` | JWT 서명 키 | CI 통합 테스트용 |
| `INTERNAL_TOKEN` | 서비스 간 내부 인증 토큰 | 배포 환경의 docker-compose에 주입 |
| `DB_URL` | 운영 PostgreSQL JDBC URL | `application-prod.yml` → `${DB_URL}` |
| `DB_USERNAME` | 운영 DB 사용자 이름 | `application-prod.yml` → `${DB_USERNAME}` |
| `DB_PASSWORD` | 운영 DB 비밀번호 | `application-prod.yml` → `${DB_PASSWORD}` |
| `EC2_HOST` | AWS EC2 퍼블릭 IP 또는 도메인 | 배포 대상 서버 |
| `EC2_SSH_KEY` | EC2 SSH 비밀키 (PEM 파일 전체 내용) | deploy 잡에서 SSH 접속 |
| `GHCR_TOKEN` | GitHub PAT (`packages:write` 권한) | Docker 이미지 GHCR 푸시 |
| `DISCORD_WEBHOOK_URL` | Discord 알림 웹훅 URL | CI 완료·실패 알림 |

---

## 3. `.env.example` 샘플

```dotenv
# ================================================
# PostgreSQL
# ================================================
POSTGRES_DB=contextq
POSTGRES_USER=contextq_user
POSTGRES_PASSWORD=         # openssl rand -hex 16
POSTGRES_HOST=localhost    # Docker: postgres
POSTGRES_PORT=5432

# ================================================
# OpenAI
# ================================================
OPENAI_API_KEY=            # platform.openai.com

# ================================================
# JWT
# ================================================
JWT_SECRET=                # openssl rand -hex 32

# ================================================
# Chroma (임베디드 — 별도 포트 불필요)
# ================================================
CHROMA_DATA_DIR=./data/chroma

# ================================================
# 서비스 간 내부 인증
# ================================================
INTERNAL_TOKEN=            # openssl rand -hex 32

# ================================================
# AI 서버 연동 (선택 — 미설정 시 localhost:8000)
# ================================================
# AI_SERVER_INTERNAL_URL=http://ai-server:8000

# ================================================
# 프론트엔드
# ================================================
VITE_API_BASE_URL=          # 빈 값 = 동일 출처 /api (Vite 프록시·nginx)

# ================================================
# 앱 환경 (선택)
# ================================================
# SPRING_PROFILES_ACTIVE=local

# ================================================
# ai-server 실행 프로필 (선택 — prod에서 INGEST_ENABLED·LLM_MOCK=true면 기동 실패)
# ================================================
# APP_PROFILE=local
# INGEST_ENABLED=false
# LLM_MOCK=false
```

---

## 4. 보안 주의사항

- `.env` 파일은 `.gitignore`에 등록되어 있다. **절대 커밋하지 않는다.**
- `.mcp.json`도 커밋하지 않는다 (GitHub PAT 포함).
- `INTERNAL_TOKEN`은 외부 노출 시 RAG 파이프라인 직접 접근이 가능하므로 운영 환경에서는 별도 시크릿 관리 도구(AWS Secrets Manager 등)를 고려한다.
- API 키 로테이션 시 GitHub Actions Secrets도 함께 갱신한다.
