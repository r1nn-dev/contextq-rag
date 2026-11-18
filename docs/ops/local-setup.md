# ContextQ-RAG 로컬 개발 환경 세팅

> **최종 수정일**: 2026-11-17

---

## 사전 준비

```bash
git --version           # 2.40+
docker --version        # 24.0+
docker compose version  # 2.20+
java --version          # 21+ (JDK)
node --version          # 20 LTS+
python --version        # 3.11+
uv --version            # 0.5+
gh --version            # GitHub CLI
```

- **uv 설치** (없는 경우):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env
```

**GitHub CLI 로그인** (없는 경우):

```bash
gh auth login
```

---

## Step 1 — 저장소 클론

```bash
git clone https://github.com/r1nn-dev/contextq-rag.git
cd contextq-rag
git branch    # * main 확인
```

---

## Step 2 — 환경 변수 설정

```bash
cp .env.example .env
```

`.env`를 열어 아래 필수 값을 채운다.

| 변수 | 설명 | 생성 방법 |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI API 키 | platform.openai.com |
| `POSTGRES_PASSWORD` | PostgreSQL 비밀번호 | `openssl rand -hex 16` |
| `JWT_SECRET` | JWT 서명 키 | `openssl rand -hex 32` |
| `INTERNAL_TOKEN` | 서비스 간 내부 인증 토큰 | `openssl rand -hex 32` |
| `VITE_API_BASE_URL` | 프론트엔드 API 호출 경로 접두사 | 빈 값 (동일 출처, Vite 프록시가 `/api`를 backend로 전달) |

---

## Step 3 — 의존성 설치

```bash
# ai-server (FastAPI)
cd ai-server && uv sync && cd ..

# backend (Spring Boot) — 첫 빌드 시 Gradle이 자동으로 의존성 다운로드
cd backend/contextq && ./gradlew dependencies --quiet && cd ../..

# frontend (React + Vite)
cd frontend && npm install && cd ..
```

> backend 없이 화면만 확인할 때는 `cd frontend && npm run dev:mock`으로 실행한다. 브라우저 안의 목 응답(`frontend/src/mocks/`)이 API 명세와 같은 형식으로 응답한다. 질문에 "양자"를 넣으면 NO_CONTEXT, "오류"를 넣으면 스트림 중 오류, "실패"를 넣으면 스트림 전 오류 화면을 확인할 수 있다.

---

## Step 4 — Docker 인프라 기동

Chroma는 ai-server 프로세스에 내장되므로 별도 컨테이너 불필요.
PostgreSQL만 먼저 올린다.

```bash
docker compose up -d postgres
docker compose ps    # postgres Up 확인
```

ai 스키마 테이블과 소스 카탈로그는 ai-server Alembic이 만든다 (`app` 스키마는 backend Flyway):

```bash
cd ai-server
uv run alembic upgrade head   # ai.sources · compare_pairs · ingest_runs · index_pointers + 카탈로그 시드
cd ..
```

인덱스 빌드는 `make ingest` (소스 하나를 새 run으로 수집 ~ 검증, local·staging 전용 — ADR-005):

```bash
# 선택: 로컬에서 인덱스를 직접 빌드하는 경우
# APP_PROFILE=local, INGEST_ENABLED=true, POSTGRES_* 접속 정보를 환경 변수로 준비한다
make ingest SOURCE=langchain_v03
make ingest SOURCE=langchain_v1x
```

> 수집 원본은 `ai-server/data/raw/{source_key}/`에 run마다 새로 받는다 (`INGEST_DATA_DIR`, `docs/specs/data-sources.md` §2).
> `INGEST_ENABLED`가 꺼져 있거나 `APP_PROFILE=prod`이면 `FORBIDDEN_IN_PROFILE`로 거부된다.

> 인덱스 스냅샷(`.tar.gz`)을 팀 공유 스토리지에서 받아 `make restore-index`로 복원하면 빌드를 생략할 수 있다.

**전체 스택을 컨테이너로 띄우는 경우** (`make up` 또는 `make -C infra up` = 기본 파일 + `infra/docker-compose.local.yml`)

- local 오버레이는 호스트의 `ai-server/data/chroma`를 컨테이너 Chroma 경로(`/app/chroma_db`)에 연결한다. 호스트에서 `make ingest`·`make activate-index`로 만든 인덱스를 컨테이너 ai-server가 그대로 검색한다. 활성 인덱스 포인터는 같은 PostgreSQL에 있으므로 활성화 CLI의 reload가 컨테이너에 바로 반영된다.
- 기본 파일만 쓰면(배포 구성) Chroma는 `chroma_data` 볼륨이라 호스트 인덱스가 보이지 않는다. 배포 환경은 스냅샷 복원으로 채운다.
- ai-server 코드가 바뀌면 이미지를 다시 빌드한다. 옛 이미지가 떠 있으면 새 내부 API가 없어 reload가 404로 끝난다.

```bash
make -C infra build && make -C infra up    # 코드 변경 후 재빌드·재기동
```
> 

---

## Step 5 — GitHub Actions Secrets 설정

> Settings → Secrets and variables → Actions → New repository secret

| Secret | 값 | 발급 방법 |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI API 키 | [platform.openai.com](https://platform.openai.com) → API keys |
| `POSTGRES_PASSWORD` | PostgreSQL 비밀번호 | `openssl rand -hex 16` |
| `JWT_SECRET` | JWT 서명 키 | `openssl rand -hex 32` |
| `EC2_HOST` | AWS EC2 퍼블릭 IP | EC2 콘솔 → 인스턴스 → Public IPv4 address |
| `EC2_SSH_KEY` | EC2 SSH 비밀키 | EC2 콘솔 → Key Pairs → PEM 파일 전체 내용 |
| `GHCR_TOKEN` | GitHub PAT | GitHub → Settings → Developer settings → PAT (Classic) · 권한: `write:packages` |
| `DISCORD_WEBHOOK_URL` | Discord 웹훅 URL | Discord 서버 설정 → 연동 → 웹후크 → 새 웹후크 → URL 복사 |

---

## Step 6 — GitHub MCP 서버 설정 (Claude Code CLI)

`.mcp.json`은 `.gitignore` 등록된 로컬 전용 파일이다. 프로젝트 루트에 직접 생성한다.

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "<your-pat>"
      }
    }
  }
}
```

- PAT 발급: GitHub → Settings → Developer settings → Personal access tokens (Classic)
- 필요 권한: `repo`

> **보안**: `.mcp.json`은 절대 커밋하지 않는다. `.gitignore`에 `.mcp.json` 항목 등록됨.

---

## 트러블슈팅

**Docker 포트 충돌**: `.env`의 `POSTGRES_HOST_PORT` (기본 5432)를 사용하지 않는 포트로 변경.

**uv sync 오류**:

```bash
cd ai-server && uv lock && uv sync
```

**Gradle 빌드 오류**:

```bash
./gradlew -p backend/contextq clean build
```

---

end.