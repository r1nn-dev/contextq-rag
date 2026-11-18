# 배포 환경 구성 및 운영 절차

> **최종 수정일:** 2026-11-18

## 1. 환경 종류

| 환경 | 목적 | 접근 방법 |
|---|---|---|
| local | 개발·테스트 | `make up` (기본 파일 + `infra/docker-compose.local.yml`, 이미지 로컬 빌드) |
| production | 서비스 운영 (EC2 단일 인스턴스, ADR-011) | GHCR 이미지 pull + `docker compose up --no-build` (§4) |

## 2. 컨테이너 구성

`infra/docker-compose.yml`이 배포 구성의 기준이다. 컨테이너는 4개다(기획서 §4.1).

| 서비스 | 이미지 | 역할 | `mem_limit` | 헬스체크 |
|---|---|---|---|---|
| `nginx` | `${IMAGE_REGISTRY}/nginx:${IMAGE_TAG}` (`infra/nginx/Dockerfile`, 프론트 빌드 포함) | React 정적 파일, `/api/**` → backend | 64m | `/healthz` |
| `backend` | `${IMAGE_REGISTRY}/backend:${IMAGE_TAG}` | 인증·이력·SSE 중계 | 600m | `/actuator/health` (DB 연결 포함) |
| `ai-server` | `${IMAGE_REGISTRY}/ai-server:${IMAGE_TAG}` | RAG 파이프라인 + Chroma 내장, 기동 시 `alembic upgrade head` | 768m | `/internal/v1/health` (소스별 ACTIVE 인덱스) |
| `postgres` | `postgres:16-alpine` | `app`·`ai` 스키마 | 256m | `pg_isready` |

- 기동 순서는 헬스체크로 맞춘다: postgres → ai-server → backend → nginx (정책서 §9.4).
  - ai-server는 소스별 ACTIVE 인덱스가 없으면 503이다. 인덱스를 복원하기 전에는 backend·nginx가 뜨지 않는다.
- `mem_limit`은 기획서 부록 A 예산의 상한이다. 예산값: PostgreSQL `shared_buffers=64MB`·`max_connections=20`, backend `-Xmx320m -XX:MaxMetaspaceSize=128m`·Tomcat 스레드 40·커넥션 풀 8, nginx worker 1, uvicorn worker 1.
- 로그는 json-file 10MB × 3개로 회전한다.
- 볼륨: `postgres_data`, `chroma_data`(Chroma). 스냅샷 입력은 `SNAPSHOT_HOST_DIR`을 ai-server `/app/data/snapshots`에 읽기 전용으로 연결한다.
- 프로젝트 이름은 `contextq`로 고정한다(컨테이너 `contextq-*`, 볼륨 `contextq_*`).
- 이미지 이름은 `${IMAGE_REGISTRY:-contextq}/<서비스>:${IMAGE_TAG:-local}`이다. 배포 태그는 git SHA만 쓰고 `latest`는 쓰지 않는다(정책서 §9.4).

## 3. nginx

설정은 이미지에 넣는다(`infra/nginx/`). `templates/*.template`은 기동 시 envsubst로 `conf.d`에 풀린다.

| 항목 | 설정 | 근거 |
|---|---|---|
| `/api/**` | 경로 그대로 `backend:8080`. `proxy_buffering off`, `proxy_read_timeout 150s` | 기획서 결정 5, ADR-003, 정책서 §2.1 |
| 레이트 리밋 | 인증 10r/m(burst 5) · 채팅 30r/m(burst 10) · 그 외 `/api` 120r/m(burst 30), IP 단위, 초과 429 | 정책서 §8.1 |
| 요청 추적 ID | 클라이언트 UUID가 없으면 생성해 `X-Request-Id`로 backend에 전달, 응답·접근 로그에 기록 | 정책서 §9.4 |
| 차단 | `/internal/**`, `/actuator/**` → 404 | 정책서 §9.4, ADR-012 |
| Swagger UI | `/swagger-ui`, `/v3/api-docs` → backend | 정책서 §9.1 |
| 보안 헤더 | CSP `default-src 'self'`, `nosniff`, `Referrer-Policy: strict-origin-when-cross-origin` | 정책서 §11 |
| 로그 | JSON 접근 로그(쿼리 문자열 없음) → stdout | 정책서 §9.4 |

채팅 한도는 `NGINX_RATE_CHAT`·`NGINX_BURST_CHAT`으로 기동 시 바꿀 수 있다(`docs/ops/env-reference.md` §1.12).

## 4. 로컬 기동

```bash
cp .env.example .env            # 값 채우기 (docs/ops/env-reference.md)
make up                         # 이미지 빌드 + 기동 → http://localhost
```

- 처음에는 인덱스가 없어 `make up`이 ai-server unhealthy로 끝난다. 인덱스를 준비한 뒤 `make up`을 다시 실행한다.
  - 스냅샷 복원: `make restore-index SNAPSHOT=data/snapshots/<스냅샷>.tar.gz` (소스마다)
  - 직접 빌드: `make ingest SOURCE=…` → `make activate-index RUN=…` (`docs/ops/local-setup.md` Step 4)
- 로컬 오버레이는 backend 8080·ai-server 8000·postgres 포트를 열고, 호스트 `ai-server/data/chroma`·`ai-server/data/snapshots`를 연결한다.
- 2026-11-18 로컬 확인: nginx 경유 SSE `meta` 0.41초, 첫 토큰 1.78초, 토큰 159개가 15.1초에 걸쳐 각각 다른 시각에 도착(버퍼링 없음).

## 5. 프로덕션 배포

(추후 작성 — EC2 초기 설정·`deploy.sh <git-sha>`·백업은 배포 스크립트 작업에서 작성)
