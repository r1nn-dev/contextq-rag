> **최종 수정일**: 2026-11-14

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
| `VITE_API_BASE_URL` | 프론트엔드 API 엔드포인트 | 로컬: `http://localhost:8080` |

---

## Step 3 — 의존성 설치

```bash
# ai-server (FastAPI)
cd ai-server && uv sync && cd ..

# backend (Spring Boot) — 첫 빌드 시 Gradle이 자동으로 의존성 다운로드
./gradlew -p backend/contextq dependencies --quiet

# frontend (React + Vite)
cd frontend && npm install && cd ..
```

---

## Step 4 — Docker 인프라 기동

Chroma는 ai-server 프로세스에 내장되므로 별도 컨테이너 불필요.
PostgreSQL만 먼저 올린다.

```bash
docker compose up -d postgres
docker compose ps    # postgres Up 확인
```

인덱스 빌드는 `make build-index` (소스 수집 ~ Chroma 적재, 최초 1회):

```bash
# 선택: 로컬에서 인덱스를 직접 빌드하는 경우
make build-index VERSION=v03
make build-index VERSION=v1x
make validate-index
```

> 인덱스 스냅샷(`.tar.gz`)을 팀 공유 스토리지에서 받아 `make restore-index`로 복원하면 빌드를 생략할 수 있다.
> 

---

## Step 5 — GitHub Actions Secrets 설정

> Settings → Secrets and variables → Actions → New repository secret
> 

| Secret | 값 |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI API 키 |
| `POSTGRES_PASSWORD` | PostgreSQL 비밀번호 |
| `JWT_SECRET` | JWT 서명 키 |
| `EC2_HOST` | AWS EC2 퍼블릭 IP |
| `EC2_SSH_KEY` | EC2 SSH 비밀키 (PEM 전체) |
| `GHCR_TOKEN` | GitHub PAT (packages write 권한) |

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

PAT 발급: GitHub → Settings → Developer settings → Personal access tokens (Classic)
필요 권한: `repo`, `read:org`

> **보안**: `.mcp.json`은 절대 커밋하지 않는다. `.gitignore`에 `.mcp.json` 항목 등록됨.
> 

### `.personal/` 초기 구조

```
.personal/
├── templates/
│   ├── dev-log-ai.md
│   ├── dev-log-backend.md
│   └── task-plan.md
└── context/
    ├── repo-guide.md
    └── contributing.md
```

| Project Space 경로 | 로컬 복사 대상 |
| --- | --- |
| `claude/dev-log-ai.md` | `.personal/templates/dev-log-ai.md` |
| `claude/dev-log-backend.md` | `.personal/templates/dev-log-backend.md` |
| `claude/repo-guide.md` | `.personal/context/repo-guide.md` |
| `claude/contributing.md` | `.personal/context/contributing.md` |

---

## Step 7 — Branch Protection 설정

PR 머지 후 `docs/ops/branch-protection.md` 체크리스트 순서대로 GitHub UI에서 직접 적용.
상세 설정 절차는 `docs/ops/branch-protection.md` 참고.

---

## Step 8 — 첫 작업 시작

```bash
git switch develop && git pull origin develop
gh issue create --title "feat(rag): 질의 재작성 프롬프트 구현" --label feat
git switch -c feat/<issue-number>-rag-query-rewrite
git push -u origin feat/<issue-number>-rag-query-rewrite
gh pr create --draft --base develop \
  --title "feat(rag): 질의 재작성 프롬프트 구현" --web
```

**커밋 스코프 기준:**

```
auth · chat · rag · ingest · eval · ui · infra · ci · docs
```

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
