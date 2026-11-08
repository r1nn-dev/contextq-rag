> **최종 수정일:** 2026-11-09
> **기준 브랜치:** `develop` (기본 브랜치), `main` (배포/릴리즈)

---

## 0. 필수 사항

### 0.1 절대 원칙

1. 작업 브랜치는 항상 `develop`에서 만든다. (`main` 직접 분기는 `hotfix/*`만 허용)
2. `main`·`develop`에는 직접 push하지 않는다. 모든 변경은 PR로만 반영한다.
3. **1 Issue = 1 Branch = 1 PR**을 기본 단위로 한다.
4. `develop` 병합은 **Squash and merge**, 병합 후 작업 브랜치는 삭제한다.
5. `ai-server/uv.lock`과 `frontend/package-lock.json`은 반드시 커밋한다. Java Gradle wrapper(`gradlew`, `gradle/wrapper/`)도 커밋한다. CI는 각각 `uv sync --locked` / `npm ci` / `./gradlew build`로 환경을 재현한다.
6. `.env`, 벡터 인덱스(`chroma_db/`), 원본 수집 데이터셋(`data/`)은 절대 커밋하지 않는다.

> **AI 협업 규칙:** `frontend/` 코드는 AI 페어프로그래밍으로 생성한다. AI 생성 코드도 셀프 리뷰를 거쳐야 하며, 커밋 전 `npm run lint && npm run build`를 반드시 확인한다.

### 0.2 작업 사이클

| 순서 | 내용 |
| --- | --- |
| 1 | GitHub Issue 생성 (템플릿 선택) |
| 2 | `develop` 최신화 → 작업 브랜치 생성 |
| 3 | 개발 및 커밋 (lefthook이 포맷·메시지 형식 검사) |
| 4 | 원격 브랜치 push |
| 5 | Draft PR 생성 (base: `develop`) |
| 6 | 자동 검사 통과 (`ci-gate` / `pr-title` / `branch-name` / `linked-issue`) |
| 7 | `Ready for review` 전환 (`gh pr ready`) |
| 8 | 셀프 리뷰 |
| 9 | `develop` 병합 (Squash and merge) → 이슈 자동 종료, 브랜치 자동 삭제 |
| 10 | `git pull origin develop` |

---

## 1. 브랜치 전략 (Git Flow)

### 1.1 브랜치 종류

| 브랜치 | 용도 | 규칙 |
| --- | --- | --- |
| `main` | 배포/릴리즈 버전 | `develop`·`hotfix/*`에서만 PR, Merge commit, 태그 부여 |
| `develop` | 개발 통합 브랜치 (기본 브랜치) | 작업 브랜치에서 PR, Squash and merge |
| `feat/*` | 신규 기능 | RAG 파이프라인, API 엔드포인트, UI 컴포넌트 추가 |
| `fix/*` | 버그 수정 | 재현 조건이 이슈에 있어야 함 |
| `refactor/*` | 구조 개선 | 동작 변경 금지. 기존 테스트가 수정 없이 통과해야 함 |
| `perf/*` | 성능·품질 개선 | PR에 Before/After 측정값 필수 |
| `test/*` | 테스트 추가 | 단위/통합/RAG 평가 테스트 |
| `docs/*` | 문서 | README, API 명세, ADR |
| `chore/*` | 설정 및 기타 | CI/CD, 의존성, 환경 설정, 실험 코드 |
| `style/*` | 포맷팅 | 동작 변경 금지 |
| `hotfix/*` | 운영 긴급 수정 | `main`에서 분기 → `main` 병합 → `develop` 역병합 |

### 1.2 브랜치 네이밍 (scope 기반)

```
<type>/<issue-number>-<scope>-<summary>

예시:
feat/12-rag-version-aware-filter
feat/15-retrieval-hybrid-search
fix/22-retrieval-chroma-metadata-filter
perf/30-retrieval-mmr-reranking
feat/40-backend-query-history-api
docs/5-adr-vector-db-selection
chore/3-ci-github-actions-setup
```

| 구성 | 규칙 |
| --- | --- |
| `type` | 위 브랜치 종류 표의 값 |
| `issue-number` | GitHub Issue 번호 (숫자만) |
| `scope` | 아래 1.3 확정 표의 값만 사용 |
| `summary` | 영문 소문자 kebab-case, 2~4단어 |

> 이 규칙은 `pr-lint.yml`의 `branch-name` 체크가 정규식으로 검사한다. 어기면 PR 병합이 막힌다.

> **scope를 넣는 이유:** `git log --oneline | grep "(rag)"` 만으로 RAG 파이프라인 변경 이력 전체를 추출할 수 있다. scope는 로그를 질의 가능한 데이터로 만드는 키다.

### 1.3 scope 정의

**이 표에 없는 scope는 사용하지 않는다.**

| 모듈 / 관심사 | scope | 위치 |
| --- | --- | --- |
| FastAPI 라우터·의존성 주입 | `api` | `ai-server/src/api/` |
| RAG 파이프라인 (체인·컨텍스트 구성) | `rag` | `ai-server/src/rag/` |
| 벡터 검색·재랭킹 | `retrieval` | `ai-server/src/retrieval/` |
| 문서 수집·파싱·청킹·임베딩 | `ingest` | `ai-server/src/ingest/` |
| 공통 DTO·설정·유틸리티 | `shared` | `ai-server/src/shared/` |
| Spring Boot 비즈니스 로직·API | `backend` | `backend/src/main/java/` |
| React 프론트엔드 | `frontend` | `frontend/src/` |
| 오프라인 수집·실험 스크립트 | `scripts` | `scripts/` |
| 프롬프트·모델·검색 설정 파일 | `configs` | `configs/` |
| 인프라 (Docker Compose) | `infra` | `infra/` |
| CI 워크플로우 | `ci` | `.github/workflows/` |
| 의존성 관리 | `deps` | `ai-server/pyproject.toml`, `backend/build.gradle`, `frontend/package.json` |
| 문서 | `docs` | `docs/` |
| 저장소 초기화·루트 설정 파일 | `setup` | 루트 (`CLAUDE.md`, `lefthook.yml`, `Makefile` 등) |

scope 판단 기준:

1. 한 PR이 두 scope를 건드리면 PR을 쪼갤 수 있는지 먼저 검토한다.
2. 쪼갤 수 없으면 변경의 주된 목적이 속한 scope 하나만 쓴다.
3. `configs/` 변경은 커밋 전 반드시 변경 의도를 이슈에 먼저 기록한다 (평가 수치가 없으면 병합 불가).

---

## 2. 커밋 규칙 (Conventional Commits)

```
<type>(<scope>)[!]: <subject>

[optional body — Why를 설명. What은 diff가 말해준다]

[optional footer — BREAKING CHANGE: 설명 / Refs: #12]
```

```
예시:
feat(rag): 버전 인식 컨텍스트 필터 구현
fix(retrieval): 버전 메타데이터 필터가 Chroma 쿼리에 미적용되는 오류 수정
perf(retrieval): 단일 의미 검색 → 하이브리드 검색 — precision@3 0.62 → 0.78
feat(ingest): LangChain 공식 문서 사이트맵 기반 URL 수집 파이프라인 구현
feat(api): 프레임워크·버전 선택 Q&A 엔드포인트 추가
feat(backend): 사용자 질의 이력 저장·조회 API 구현
feat(api)!: /api/v1/qa 응답 스키마에 sources 배열 추가
chore(deps): langchain 0.3.7 업그레이드
docs(adr): 0001 Vector DB 선택 (Chroma vs Weaviate) ADR 추가
perf(rag): faithfulness 0.71 → 0.83 — 시스템 프롬프트 개선
```

### 타입 의미

| 타입 | 의미 |
| --- | --- |
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 코드 개선 (기능 변경 없음) |
| `perf` | 성능·품질·지표 개선 (측정값 필수) |
| `docs` | 문서 수정 |
| `test` | 테스트 코드 |
| `chore` | 설정, 빌드, 기타 작업 |
| `style` | 포맷팅, import 정리 |
| `hotfix` | 긴급 수정 |

### 작성 기준

- 한 커밋 = 한 목적. 기능 구현 / 테스트 / 리팩터링 / 포맷팅은 분리한다.
- 제목은 명령형·현재형, 마침표 없이 50자 이내. 한글 사용 가능.
- `perf` 커밋은 body에 측정값 또는 평가셋 버전·임베딩 모델·top-k 값을 남긴다.
- `!` (Breaking change): 공개 계약(REST API 응답 스키마, `configs/` 파일 구조, RAG 체인 입출력 인터페이스)을 깨면 `!` 추가.
- 형식은 lefthook `commit-msg` 훅이 로컬에서 검사한다.

---

## 3. 이슈 관리

> **1 Issue = 1 Branch = 1 PR** — 작업 단위와 브랜치를 1:1로 맞춰야 추적성이 확보된다.

- 이슈 제목: `<type>(<scope>): <subject>` 형식
- 이슈 단위: 반나절~2일 내 끝나는 크기. 그 이상이면 쪼갠다.
- 완료 기준(DoD): 이슈 구현 항목 전부 반영 + 테스트 통과 + 문서 갱신 + PR 병합

### 3.1 라벨 체계

| 축 | 라벨 | 부여 방식 |
| --- | --- | --- |
| type | `feat` `fix` `refactor` `perf` `test` `docs` `chore` `style` `hotfix` | 이슈·PR 제목의 type에서 자동 |
| status | `blocked` | 수동 |
| action | `eval` | 수동 — PR에 붙이면 RAG 평가 워크플로우 실행 |

> priority·size·area는 GitHub Projects 커스텀 필드(Priority·Effort·Area)로 관리한다.

### 3.2 이슈 템플릿

#### 3.2.1 기능 구현 — `1-feat.md`

기능 구현 이슈 템플릿: [`.github/ISSUE_TEMPLATE/1-feat.md`](.github/ISSUE_TEMPLATE/1-feat.md)

#### 3.2.2 버그 수정 — `2-fix.md`

버그 수정 이슈 템플릿: [`.github/ISSUE_TEMPLATE/2-fix.md`](.github/ISSUE_TEMPLATE/2-fix.md)

#### 3.2.3 일반 작업 — `3-chore.md`

일반 작업 이슈 템플릿: [`.github/ISSUE_TEMPLATE/3-chore.md`](.github/ISSUE_TEMPLATE/3-chore.md)

---

## 4. Pull Request 규칙

### 4.1 PR 규칙

| 규칙 | 강제 방식 |
| --- | --- |
| base는 `develop` (릴리즈·hotfix만 `main`) | `branch-name` 체크 |
| 제목은 `<type>(<scope>): <subject>` | `pr-title` 체크 |
| 본문에 `Closes #이슈번호` | `linked-issue` 체크 |
| 빌드·테스트·린트 통과 | `ci-gate` 체크 |

- Draft로 먼저 연다. CI를 Draft 상태에서 통과시키고 `Ready for review`로 전환한다.
- PR 크기: 변경 300줄 이내 권장 (lock 파일, 자동 생성 파일 제외).
- `configs/` 변경은 PR 본문에 반드시 평가 수치(Before/After)를 포함해야 병합한다.
- `Closes #이슈번호`는 기본 브랜치(`develop`)에 병합될 때만 이슈를 자동으로 닫는다.
- 릴리즈 PR 제목은 `chore(release): v1.2.0`, hotfix 역병합 PR 제목은 `chore(release): main → develop 동기화`로 쓴다.

### 4.2 PR 본문 템플릿 — `pull_request_template.md`

**작성 공통 규칙**

- 제목은 연결된 이슈 제목을 그대로 쓴다. (Squash 시 이 제목이 커밋 메시지가 된다)
- `(선택)`이 붙은 섹션만 삭제할 수 있다.
- 체크박스는 직접 확인한 것만 체크한다.
- 수치·로그는 실행 결과를 복사해서 붙인다. 기억으로 쓰지 않는다.

PR 템플릿: [`.github/pull_request_template.md`](.github/pull_request_template.md)

### 4.3 병합(merge) 정책

| 대상 | Approve | 병합 방식 |
| --- | --- | --- |
| 작업 브랜치 → `develop` | 셀프 리뷰 | Squash and merge |
| `develop` → `main` (릴리즈) | 셀프 리뷰 | Merge commit |
| `hotfix/*` → `main` | 셀프 리뷰 | Merge commit |
| `main` → `develop` (역병합) | 없음 | Merge commit |

### 4.4 셀프 리뷰

PR을 올린 뒤 Files changed 탭을 처음부터 끝까지 직접 읽는다.

- [ ] 이 PR만 revert했을 때 시스템이 이전 상태로 돌아가는가
- [ ] 변경 줄 수가 300줄을 넘지 않는가, 넘는다면 쪼갤 수 없는 이유가 있는가
- [ ] 6개월 뒤의 내가 이 diff와 PR 본문만 보고 의도를 이해할 수 있는가

---

## 5. 코드 스타일

### 5.1 Python (ai-server/)

```bash
# 린트 (자동 수정 포함)
uv run ruff check --fix .

# 포맷
uv run ruff format .

# 타입 검사
uv run mypy src

# 테스트
uv run pytest -q                  # 단위 테스트 (llm/eval 마커 제외)
uv run pytest -m llm              # LLM 호출 테스트 (로컬)
uv run pytest -m eval             # RAG 평가 (평가셋 전체, 비용 발생)
```

`ai-server/pyproject.toml` 설정:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.12"
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
  "llm: 실제 LLM API를 호출하는 테스트",
  "eval: RAG 평가 테스트 (평가셋 전체, 비용 발생)",
]
addopts = "-m 'not llm and not eval'"
```

### 5.2 Java (backend/)

```bash
# 포맷 검사 (Spotless — Google Java Format)
./gradlew spotlessCheck

# 포맷 자동 수정
./gradlew spotlessApply

# 빌드 및 테스트
./gradlew build

# 테스트만
./gradlew test
```

`backend/build.gradle` 설정 (Spotless 최소 구성):

```groovy
plugins {
    id 'com.diffplug.spotless' version '6.25.0'
}

spotless {
    java {
        googleJavaFormat('1.22.0')
        removeUnusedImports()
        trimTrailingWhitespace()
        endWithNewline()
    }
}
```

### 5.3 Frontend (frontend/)

```bash
cd frontend
npm run lint      # ESLint
npm run format    # Prettier
npm run build     # 빌드 검사
npm test          # 단위 테스트 (Vitest 또는 Jest)
```

> AI 페어프로그래밍으로 생성된 프론트엔드 코드는 `npm run lint && npm run build`를 반드시 통과해야 커밋 가능하다.

### 5.4 lefthook (로컬 훅)

`lefthook.yml`이 루트에 있고, `lefthook install` 후 자동으로 검사한다.

- `pre-commit`: ruff lint·format 자동 수정, nbstripout (노트북 출력 셀 제거)
- `commit-msg`: Conventional Commits 형식 검사
- `pre-push`: `main`·`develop` 직접 push 차단

```yaml
pre-commit:
  parallel: true
  commands:
    ai-server-lint:
      glob: "ai-server/**/*.py"
      run: cd ai-server && uv run ruff check --fix . && uv run ruff format .
      stage_fixed: true
    scripts-lint:
      glob: "scripts/**/*.py"
      run: uv run ruff check --fix scripts/ && uv run ruff format scripts/
      stage_fixed: true
    notebook-strip:
      glob: "*.ipynb"
      run: uvx nbstripout {staged_files}   # 출력 셀 제거: diff 노이즈·API 키 노출 방지
      stage_fixed: true

commit-msg:
  commands:
    conventional:
      run: |
        msg=$(head -n1 {1})
        pattern='^((feat|fix|refactor|perf|test|docs|chore|style|hotfix)(\([a-z0-9-]+\))?!?: .+|Merge .+|Revert .+|(fixup|squash)! .+|WIP.*)$'
        if ! echo "$msg" | grep -Eq "$pattern"; then
          echo "❌ 커밋 메시지 형식: <type>(<scope>): <subject>"
          echo "   입력: $msg"
          exit 1
        fi

pre-push:
  commands:
    protect-branch:
      run: |
        branch=$(git symbolic-ref --short HEAD)
        if [ "$branch" = "main" ] || [ "$branch" = "develop" ]; then
          echo "❌ $branch 브랜치에는 직접 push할 수 없습니다. PR을 사용하세요."
          exit 1
        fi
```

> 훅은 로컬 편의 장치이고, 강제는 CI가 한다. `--no-verify`로 우회할 수 있기 때문이다.

---

## 6. 작업 흐름

### 6.1 이슈 검토

- 이슈는 PR의 초안이다. 작업 시작 전 구현 내용을 다시 읽고 모호한 항목이 있으면 이슈부터 고친다.
- 작업 중 범위가 커지면 이슈 본문을 늘리지 않고 후속 이슈를 새로 만든다.

### 6.2 작업 시작 전 — 항상 develop 최신 상태로 맞추기

작업을 시작할 때마다 반드시 실행한다. 건너뛰면 나중에 충돌이 생긴다.

```bash
# 새 작업 시작
git switch develop                           # develop 브랜치 이동
git pull origin develop                      # develop 최신화
git switch -c feat/이슈번호-scope-summary     # 본인 브랜치 생성
```

```bash
# 작업 중 develop이 업데이트된 경우 (커밋 완료 상태)
git status
git switch develop
git pull origin develop
git switch feat/이슈번호-scope-summary
git merge develop
```

```bash
# 작업 중 develop이 업데이트된 경우 (미커밋 변경사항 있음)
git stash push -m "작업 중 내용"
git switch develop
git pull origin develop
git switch feat/이슈번호-scope-summary
git merge develop
git stash pop
```

**현재 브랜치가 어디인지 모를 때:**

```bash
git branch    # 브랜치 목록. * 표시가 현재 브랜치
git status    # 현재 브랜치 + 변경된 파일 목록
```

### 6.3 코드 작업

평소처럼 IDE에서 코드를 작성한다.

#### 6.3.1 작업 내용 저장 (commit)

```bash
git add .
git commit -m "feat(rag): 버전 인식 컨텍스트 필터 구현"
```

**특정 파일만 선택해서 커밋하고 싶을 때:**

```bash
git add -p
git add ai-server/src/rag/chain.py
git commit -m "feat(rag): 버전 인식 컨텍스트 필터 구현"
```

#### 6.3.2 GitHub에 올리기 (push)

```bash
git push -u origin feat/12-rag-version-aware-filter   # 최초 1회만 -u
git push origin feat/12-rag-version-aware-filter
```

#### 6.3.3 IDE 종료할 때

별도 명령어 없이 그냥 닫으면 된다.

### 6.4 Pull Request(PR) 생성

```bash
gh pr create --draft --base develop --web
```

웹에서 직접 만들 때:

1. GitHub 레포지토리 페이지 접속
2. `Compare & pull request` 버튼 클릭
3. **base: `develop` ← compare: 본인 브랜치** 확인
4. 제목을 이슈 제목과 동일하게 입력, 본문 작성
5. `Create pull request` 옆 ▼ → **`Create draft pull request`**

### 6.5 PR 리뷰 & 병합

**Draft 단계:**

1. 필수 체크 4개 통과 확인. 실패하면 `Details`에서 로그 확인 후 같은 브랜치에 수정 커밋.
2. 프롬프트·검색 파라미터·임베딩 모델을 바꿨다면 `eval` 라벨을 붙여 평가 결과를 받는다.
3. 준비되면 `Ready for review` (`gh pr ready`)

**셀프 리뷰 체크 포인트:**

- [ ] 의도대로 동작하는가 — 이슈의 구현 내용·통과 기준을 충족하는가
- [ ] 컨벤션을 지켰는가 — 네이밍, 패키지 위치, scope
- [ ] 예외·엣지 케이스 처리가 있는가 — LLM 호출 실패, 빈 검색 결과, DB 타임아웃
- [ ] 계약(API 스키마, ERD, `configs/` 구조)이 바뀌었다면 `docs/specs/`가 함께 고쳐졌는가

**병합:**

1. 셀프 리뷰 완료
2. `Squash and merge` → 커밋 메시지가 PR 제목과 같은지 확인 → `Confirm`
3. 작업 브랜치 자동 삭제 확인
4. `git pull origin develop`

### 6.6 병합 후 pull — develop 최신화

```bash
git switch feat/본인브랜치
git pull origin develop
```

```bash
# 내 PR이 병합된 뒤 로컬 정리
git switch develop && git pull origin develop
git fetch -p
git branch -d feat/12-rag-version-aware-filter
```

---

## 7. 충돌(Conflict) 해결

### 7.1 충돌이 발생한 경우

```
<<<<<<< HEAD
내 브랜치의 코드
=======
develop에서 온 코드
>>>>>>> develop
```

어느 코드를 남길지 직접 선택하고 저장한 뒤 다시 커밋한다.

### 7.2 충돌 해결하기

1. IntelliJ: `Git → Resolve Conflicts` / VS Code: 충돌 부분 상단의 `Accept Current / Incoming / Both` 버튼
2. `<<<`, `===`, `>>>` 마커를 모두 삭제하고 최종 코드만 남긴다.
3. 양쪽 로직이 모두 필요하면 직접 합쳐서 작성한다.
4. 테스트를 다시 돌린 뒤 커밋한다.

```bash
git add .
git commit -m "chore(<scope>): develop 병합 충돌 해결"
```

> **`uv.lock` 충돌**: 직접 고치지 않는다. `ai-server/pyproject.toml` 충돌만 해결한 뒤 `cd ai-server && uv lock`으로 재생성한다.
>
> **`package-lock.json` 충돌**: 직접 고치지 않는다. `frontend/package.json` 충돌만 해결한 뒤 `cd frontend && npm install`로 재생성한다.

### 7.3 충돌 방지 규칙

- `ai-server/pyproject.toml`, `uv.lock` 변경은 커밋 전 이슈에 먼저 기록한다.
- `backend/build.gradle` 변경은 커밋 전 이슈에 먼저 기록한다.
- `frontend/package-lock.json`은 직접 편집하지 않는다. `npm install`로 재생성한다.
- `configs/` 변경은 평가 수치 없이 병합하지 않는다.
- `infra/docker-compose.yml` 변경은 커밋 전 이슈에 먼저 기록한다.
- `docs/specs/` (API·ERD 명세) 변경은 연관 구현 PR과 반드시 함께 반영한다.
- 작업 시작 전 `git pull origin develop`은 무조건 실행한다.

---

## 8. 실수했을 때 되돌리기

### 8.1 파일 수정 취소 (커밋 전)

```bash
git restore 파일명
git restore .
```

> **주의:** 이 명령어는 되돌릴 수 없다. 신중하게 사용할 것.

### 8.2 git add 취소 (커밋 전)

```bash
git restore --staged <file>
git restore --staged .
```

### 8.3 커밋 메시지 수정 (push 전에만 가능)

```bash
git commit --amend -m "<type>(<scope>): <subject>"
```

> **push한 후에는 사용하지 않는다.** 어차피 Squash merge 시 PR 제목으로 대체된다.

### 8.4 마지막 커밋을 통째로 취소하고 싶을 때 (push 전에만 가능)

```bash
git reset --soft HEAD~1    # 커밋만 취소, 변경사항은 유지
git reset --hard HEAD~1    # 커밋과 변경사항 모두 폐기
```

### 8.5 이미 push/병합된 커밋 되돌리기

```bash
git revert <commit-hash>
```

`develop`에 병합된 PR을 되돌릴 때는 PR 페이지의 `Revert` 버튼을 쓰면 되돌리는 PR이 자동 생성된다.

### 8.6 실수로 main 브랜치에서 작업했을 때

```bash
# 커밋 전
git switch -c feat/이슈번호-scope-summary
```

```bash
# 이미 커밋까지 했다면 (push 전)
git stash
git switch -c feat/이슈번호-scope-summary
git switch main
git reset --hard origin/main
git switch feat/이슈번호-scope-summary
git stash pop
```

### 8.7 뭔가 크게 잘못했을 때

```bash
git reflog
git reset --hard <hash>
```

### 8.8 비밀키를 커밋했을 때

1. **키부터 폐기·재발급한다.** public 레포에 올라간 키는 수 분 안에 수집된다고 가정한다.
2. 코드에서 제거하고 `.env`로 옮긴 커밋을 올린다.
3. 히스토리에서 지우려면 `git filter-repo`가 필요하다. 키를 폐기했다면 생략할 수 있다.

---

## 9. 운영 규칙

### 9.1 릴리즈 (`develop → main`)

```bash
# PR: base main ← compare develop, 제목 chore(release): v0.1.0
git switch main && git pull origin main
git tag -a v0.1.0 -m "release: v0.1.0"
git push origin v0.1.0
gh release create v0.1.0 --generate-notes
```

버전은 SemVer(`MAJOR.MINOR.PATCH`). `!`가 붙은 PR이 포함됐다면 MINOR를 올린다 (1.0 이전 기준).

### 9.2 hotfix

```bash
git switch main && git pull origin main
git switch -c hotfix/이슈번호-scope-summary
# 수정 → PR(base: main) → Merge commit → 태그(PATCH 증가)
```

병합 후 **역병합 PR**을 만든다.

```bash
gh pr create --base develop --head main --title "chore(release): main → develop 동기화" --body "hotfix #이슈번호 반영"
# Merge commit으로 병합 (squash 금지)
```

역병합하지 않으면 다음 릴리즈에서 같은 버그가 되살아난다.

### 9.3 커밋 서명 / 잔디

Squash merge 커밋은 GitHub 계정 이메일로 기록된다. 작업 PC마다 이메일이 다르면 기여가 누락된다.

```bash
git config --local user.email "your@email.com"
```

### 9.4 ADR (Architecture Decision Record)

`docs/adr/NNNN-<영문-슬러그>.md`로 작성한다. 아래 두 조건을 모두 만족하는 기술 결정에만 작성한다:

1. 실제로 검토한 대안이 2개 이상 있었다.
2. 나중에 바꾸려면 여러 모듈 수정이 필요하다. (Vector DB, 임베딩 모델, RAG 체인 아키텍처, DB 스키마, 청킹 전략 등)

ADR은 수정하지 않는다. 결정이 바뀌면 새 ADR을 쓰고 이전 ADR 상태를 `대체됨(→ NNNN)`으로 바꾼다.

### 9.5 LLMOps 운영 규칙

**프롬프트·설정:**

- `configs/prompts/`, `configs/retrieval/`, `configs/models/` 아래 YAML 파일로만 관리한다.
- 코드에 프롬프트 문자열을 하드코딩하지 않는다.
- 프롬프트·검색 파라미터 변경은 `feat` 또는 `perf`로 올리고 PR에 평가 수치(Before/After)를 필수로 붙인다.

**평가셋:**

- `ai-server/tests/datasets/<이름>_v<번호>.jsonl`로 버전을 파일명에 박는다.
- 평가셋 변경은 별도 PR로 분리한다. 로직과 평가셋을 같이 바꾸면 Before/After 비교가 성립하지 않는다.
- 측정 결과에는 평가셋 버전, LLM 모델명, 임베딩 모델, top-k 값, 채점자 모델을 함께 적는다.

**RAG 평가 지표:**

| 지표 | 설명 | 도구 |
|---|---|---|
| Faithfulness | LLM 답변이 검색 컨텍스트에 근거하는 비율 | RAGAS |
| Answer Relevance | 답변이 질문과 관련된 비율 | RAGAS |
| Context Precision@k | 검색된 k개 문서 중 관련 문서 비율 | RAGAS |
| Context Recall | 관련 문서가 검색 결과에 포함된 비율 | RAGAS |

**데이터:**

- 벡터 인덱스(`chroma_db/`), 원본 수집 데이터(`data/`)는 커밋하지 않는다.
- 재생성 명령(수집 → 파싱 → 임베딩 순서)을 `docs/ops/data-pipeline.md`에 기록한다.

**테스트 계층:**

| 계층 | 대상 | LLM 호출 | 실행 시점 |
| --- | --- | --- | --- |
| 단위 | 청킹, 파싱, 메타데이터 필터 조건, 프롬프트 조립 | Mock | 매 커밋 (CI) |
| LLM | 실제 Q&A 응답 품질, 출처 URL 정확성, 에러 처리 | 실제 | `eval` 라벨 / 로컬 `pytest -m llm` |
| 평가 | 평가셋 전체 RAG 지표 (Faithfulness, Precision@k 등) | 실제 | `eval` 라벨 / 릴리즈 전 |

---

## 10. 자주 쓰는 명령어 모음

```bash
# 상태 확인
git status
git branch
git log --oneline --graph -20
git log --oneline | grep "(rag)"           # scope별 이력
git diff
git diff --staged

# 브랜치
git switch develop
git switch -c feat/이슈번호-scope-summary
git branch -d feat/이슈번호-scope-summary
git fetch -p

# 기본 작업
git add .
git add -p
git commit -m "<type>(<scope>): <subject>"
git push -u origin feat/이슈번호-scope-summary
git pull origin develop

# PR
gh pr create --draft --base develop --web
gh pr checks
gh pr ready
gh pr merge --squash

# 이슈와 연결된 브랜치 한 번에 생성
gh issue develop 12 --base develop --name feat/12-rag-version-aware-filter --checkout

# 임시 저장 (stash)
git stash push -m "작업 중 내용"
git stash pop
git stash list

# Python (ai-server/)
cd ai-server
uv sync
uv run ruff check --fix . && uv run ruff format .
uv run mypy src
uv run pytest -q
uv run pytest -m llm
uv run pytest -m eval

# lock 파일 재생성
uv lock

# Java (backend/)
cd backend
./gradlew spotlessApply
./gradlew build
./gradlew test

# Frontend (frontend/)
cd frontend
npm install
npm run lint
npm run format
npm run build
npm test

# lock 파일 재생성
npm install   # package-lock.json 재생성
```

---

## 메모

이 문서의 모든 규칙은 `pr-lint.yml` CI 체크와 lefthook 훅으로 강제된다. 규칙이 바뀌면 이 파일과 워크플로우를 함께 수정한다.

---

end.
