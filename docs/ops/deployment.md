# 배포 환경 구성 및 운영 절차

> **최종 수정일:** 2026-11-18

## 1. 환경 종류

| 환경 | 목적 | 접근 방법 |
|---|---|---|
| local | 개발·테스트 | `make up` (기본 파일 + `infra/docker-compose.local.yml`, 이미지 로컬 빌드) |
| production | 서비스 운영 (EC2 단일 인스턴스, ADR-011) | GHCR 이미지 pull + `deploy.sh <git-sha>` (§5) |

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

### 2.1 이미지 빌드·푸시 (`.github/workflows/release.yml`)

| 항목 | 내용 |
|---|---|
| 트리거 | `main` push, 수동 실행(선택한 브랜치 HEAD — 배포 리허설) |
| 이미지 | `ghcr.io/<owner>/<repo>/{nginx,backend,ai-server}:<40자 git SHA>` — 운영 `IMAGE_REGISTRY=ghcr.io/<owner>/<repo>`, `IMAGE_TAG=<sha>` |
| 인증 | 푸시는 워크플로 기본 `GITHUB_TOKEN`(`packages: write`). 운영 서버 pull은 `read:packages` PAT(`GHCR_TOKEN`, 서버에서만 입력) 또는 패키지 공개 설정 |
| 캐시 | GitHub Actions 캐시(서비스별 scope) |
| 결과 | 실행 요약에 이미지 경로와 `deploy.sh <sha>` 인자를 남긴다 |

- 서버 배포는 워크플로가 하지 않는다. 운영 서버에서 `deploy.sh <git-sha>`로 pull·기동한다(§5).

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

운영 서버 스크립트는 `infra/scripts/`에 있고 모두 `infra/scripts/compose-prod.sh`(기본 파일 + `infra/docker-compose.prod.yml` + 운영 환경 파일)로 Compose를 부른다.

| 경로 (서버) | 내용 |
|---|---|
| `/opt/contextq/app` | 저장소 체크아웃 — `deploy.sh`가 배포 SHA로 맞춘다 |
| `/opt/contextq/contextq.env` | 운영 환경 파일 (`chmod 600`, `docs/ops/env-reference.md` §4) |
| `/opt/contextq/release.env` | 배포 중인 `IMAGE_REGISTRY`·`IMAGE_TAG` (`deploy.sh`가 쓴다) |
| `/opt/contextq/deployments.log` | 배포 이력 `<UTC 시각> <sha> <ok\|failed\|waiting-index>` |
| `/opt/contextq/{snapshots,backups,logs}` | 인덱스 스냅샷 · DB 백업(최근 2개) · 크론 로그 |

### 5.1 AWS 사전 확인 (콘솔, 사용자)

- 계정 조건(개설일·플랜·잔여 크레딧) 확인, AWS Budgets 알림 50%·80% (기획서 §9.5).
- EC2 `t3.small`(서울 리전, Ubuntu 24.04 LTS), 크레딧 사양 **standard**, EBS gp3 20GiB, Elastic IP (기획서 결정 6, ADR-011). 부하 테스트·최종 시연 기간에만 `c7i-flex.large`로 일시 증설.
- 보안 그룹 인바운드: 22(관리자 IP만) · 80 · 443.
- IAM 인스턴스 역할: S3 버킷의 `index-snapshots/`·`pg-backups/` 읽기·쓰기.
- 도메인 A 레코드 → Elastic IP (Let's Encrypt 발급에 필요).
- CloudWatch `CPUCreditBalance` 알림 (기획서 §9.5).

### 5.2 초기 설정 (1회)

```bash
sudo git clone https://github.com/<owner>/<repo>.git /opt/contextq/app   # ec2-setup 후 소유자를 ubuntu로
sudo bash /opt/contextq/app/infra/scripts/ec2-setup.sh                    # 시간대·스왑·Docker·AWS CLI·certbot·크론
sudo chown -R ubuntu:ubuntu /opt/contextq/app
# 다시 로그인(docker 그룹) 후 운영 환경 파일 작성 — 값은 별도 터미널에서 입력
install -m 600 /dev/null /opt/contextq/contextq.env && vi /opt/contextq/contextq.env
echo "<read:packages PAT>" | docker login ghcr.io -u <github-user> --password-stdin   # GHCR 패키지가 비공개일 때
```

### 5.3 HTTPS 인증서 (1회, 첫 배포 전)

```bash
sudo bash /opt/contextq/app/infra/scripts/tls-init.sh <도메인> <알림 이메일>
```

- nginx가 80 포트를 쓰기 전에 standalone으로 발급한다. 갱신은 certbot 타이머가 하고, 갱신할 때만 nginx를 잠시 멈췄다 띄운다(60일마다 수 초).
- 배포 nginx는 HTTP → HTTPS 301, HSTS 1년(`infra/nginx/prod/default.conf.template`, 정책서 §11).

### 5.4 배포·롤백

```bash
/opt/contextq/app/infra/scripts/deploy.sh <40자 git SHA>      # release.yml이 그 SHA로 이미지를 올린 뒤
/opt/contextq/app/infra/scripts/deploy.sh --previous           # 직전 성공 SHA
/opt/contextq/app/infra/scripts/deploy.sh "$(/opt/contextq/app/infra/scripts/deploy.sh --previous)"   # 롤백
```

1. 저장소를 같은 SHA로 체크아웃(Compose·nginx 설정 일치) → `release.env` 기록 → 이미지 pull. pull이 실패하면 이전 기록으로 되돌리고 멈춘다(컨테이너 변경 없음).
2. postgres·ai-server 기동(ai 스키마 마이그레이션) → 헬스체크.
3. 전체 기동 → 4개 헬스체크 → 이력 `ok`. 실패하면 이력 `failed`와 롤백 명령을 출력한다.
4. 첫 배포처럼 인덱스가 없으면 ai-server가 503이라 `waiting-index`로 멈춘다(종료 코드 3) → §5.5 복원 후 같은 명령을 다시 실행한다.

### 5.5 인덱스 스냅샷 복원

```bash
# 로컬: make snapshot-index RUN=<id> → infra/scripts/index-snapshot-s3.sh upload <파일>
/opt/contextq/app/infra/scripts/restore-index.sh snapshot-langchain_v03-run<id>.tar.gz
/opt/contextq/app/infra/scripts/restore-index.sh snapshot-langchain_v1x-run<id>.tar.gz
```

- S3에서 받아 sha256을 확인하고, ai-server 컨테이너 안에서 같은 run id로 RESTORING → VALIDATING → READY → 활성화한다(정책서 §4.5). 스모크 질문 임베딩에 OpenAI 키를 쓴다.
- 같은 run id가 이미 있으면 거부된다. 실패 run은 FAILED로 남고 기존 ACTIVE는 그대로다.

### 5.6 백업·복구 (RPO 24시간, RTO 1시간)

- 크론(`/etc/cron.d/contextq`)이 매일 03:00 KST에 `pg-backup.sh`를 실행한다: `pg_dump -Fc` → `BACKUP_S3_URI`, 7일 지난 백업 삭제, 서버에는 최근 2개.
- 인덱스는 스냅샷 자체가 백업이다(정책서 §9.4).

```bash
/opt/contextq/app/infra/scripts/pg-backup.sh                                   # 수동 백업
/opt/contextq/app/infra/scripts/pg-restore.sh contextq-YYYYMMDD-HHMM.dump       # 리허설 — 임시 DB, 운영 DB 변경 없음
/opt/contextq/app/infra/scripts/pg-restore.sh contextq-YYYYMMDD-HHMM.dump --live --yes   # 실제 복원
```

- 리허설은 임시 DB `contextq_restore_check`에 복원해 주요 테이블 행 수와 소요 시간을 출력하고 지운다. 배포 후 1회 실행해 결과를 §5.9에 기록한다.
- 실제 복원은 nginx·backend·ai-server를 멈추고 운영 DB를 백업 시점으로 되돌린 뒤 다시 기동한다. 백업 이후 데이터는 사라진다.

### 5.7 전시회 한도 전환 (정책서 §8.1)

```bash
/opt/contextq/app/scripts/exhibition-profile.sh apply    # 채팅 60r/m(burst 20), 게스트 신규 세션 IP당 60개/시간
/opt/contextq/app/scripts/exhibition-profile.sh reset    # 다음 날 00:00 원복
/opt/contextq/app/scripts/exhibition-profile.sh status
```

- 운영 환경 파일 값만 바꾸고 nginx·backend를 다시 만든다(backend 재기동 약 1분). 리허설 결과가 부족하면 `EXHIBITION_CHAT_RATE`·`EXHIBITION_CHAT_BURST`·`EXHIBITION_GUEST_SESSIONS`로 값을 바꿔 `apply`한다.

### 5.8 메모리 실측

```bash
/opt/contextq/app/infra/scripts/mem-report.sh    # docker stats + free → 마크다운 표
```

- 배포 직후 실행해 기획서 부록 A 예산표를 실측값으로 바꾼다. 기준: 상주 합계 ≤ 1.75GB, 평시 스왑 ≤ 256MB(정책서 §11).

### 5.9 운영 기록

| 항목 | 값 | 측정일 |
|---|---|---|
| 배포 URL | | |
| 첫 배포 SHA | | |
| 메모리 실측 (컨테이너 합계 / 스왑) | | |
| 백업 복원 리허설 소요 시간 | | |
| 인덱스 복원 (소스별 run · 소요 시간) | | |
