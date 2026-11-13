# 시스템 설계 명세서 (SDD)

| 항목 | 값 |
| --- | --- |
| **상태** | 초안 |
| **날짜** | 2026-11-06 |
| **관련** | `기획서_v1.md` §5·§6·§8.5, `claude/interfaces.md`, `DevDocs-RAG API v1.md` |

---

## 1. 기능 명세

기능은 사용자가 직접 체감하는 행동 단위로 정의한다. 각 기능은 **문제 → 동작 방식 → 입출력 → 예외 → 인수 기준** 순서로 기술한다.

---

### 1.1 버전 선택 RAG 검색

**문제:** LangChain v0.3과 v1.x는 API·개념이 혼재되어 있다. 특정 버전 문서만 검색하지 않으면 LLM이 버전이 다른 답변을 생성할 수 있다.

**동작 방식:**

1. 사용자가 버전(`v0.3` / `v1.x`)과 질문을 입력한다.
2. ai-server는 선택된 버전에 대응하는 Chroma 컬렉션(`langchain_v03_run{active_id}` 또는 `langchain_v1x_run{active_id}`)에서 k개 청크를 검색한다.
3. 검색된 청크를 컨텍스트로 LLM(GPT-4o-mini)에 전달하고 답변을 SSE로 스트리밍한다.
4. 응답 첫 번째 이벤트(`meta`)에 출처 목록을 먼저 전송하고, 이후 `token` 이벤트로 답변 텍스트를 스트리밍한다.

**입력:**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `source_key` | `"langchain_v03"` \| `"langchain_v1x"` | 검색 대상 소스 식별자 |
| `question` | string | 사용자 질문 (최대 1,000자) |
| `conversation_id` | string? | 멀티턴 연속 시 이전 대화 ID |

**출력 (SSE 이벤트 순서):**

```
event: meta
data: {"sources": [{"heading_path": "...", "permalink": "...", "chunk_id": "...", "similarity": 0.87}], "source_key": "langchain_v03"}

event: token
data: {"text": "LangChain v0.3에서 Memory는 ..."}

event: token
data: {"text": " ConversationBufferMemory를 사용합니다."}

event: done
data: {"status": "OK", "finish_reason": "stop"}
```

**예외:**

| 조건 | 동작 |
| --- | --- |
| 최대 유사도 < τ (NO_CONTEXT) | LLM 호출 없이 `NO_CONTEXT` SSE 응답 반환 (1.3 참조) |
| source_key가 미등록 값 | 400 Bad Request |
| Chroma 컬렉션 없음 | 503 Service Unavailable |
| OpenAI API timeout | 504 Gateway Timeout |
| 스트림 중 클라이언트 연결 끊김 | LLM 호출 중단, 토큰 과금 최소화 |

**인수 기준 (RAG-01, RAG-07):**
- [ ] `meta` 이벤트가 첫 번째 `token` 이벤트보다 먼저 도달한다.
- [ ] `meta.sources` 배열에 `heading_path`와 `permalink`가 모두 포함된다.
- [ ] 버전 필터가 활성화된 상태에서 반환된 모든 청크의 `source_key` 필드가 요청 버전과 일치한다.
- [ ] SSE 스트림이 `done` 이벤트로 정상 종료된다.

---

### 1.2 Permalink 출처 반환

**문제:** LLM 답변의 근거가 된 문서 위치를 모르면 답변의 신뢰성을 검증하기 어렵다.

**동작 방식:**

1. Retriever가 반환한 각 청크에서 `heading_path`와 `permalink`를 추출한다.
2. `permalink` 는 Chroma에 색인할 때 기록된 GitHub 커밋 SHA 고정 URL이다. 인덱스가 갱신되어도 이전 대화의 출처 URL이 깨지지 않는다.
3. `meta` 이벤트를 통해 프론트엔드에 전달하고, 클라이언트는 출처 카드로 렌더링한다.

**출력 (`source` 객체):**

| 필드 | 설명 |
| --- | --- |
| `chunk_id` | 청크 식별자 |
| `heading_path` | 문서 내 헤딩 계층 경로 (예: `"How-To > Add Memory > ConversationBufferMemory"`) |
| `permalink` | `https://github.com/langchain-ai/langchain/blob/{SHA}/docs/docs/{path}#{anchor}` |
| `source_key` | `"langchain_v03"` \| `"langchain_v1x"` |
| `similarity` | 유사도 점수. 범위: 0.0~1.0 |

**인수 기준 (RAG-05):**
- [ ] 반환된 `permalink`에 커밋 SHA가 포함된다 (40자 hex 패턴 검증).
- [ ] `permalink`가 GitHub 웹에서 실제로 열리는 URL임을 인덱스 빌드 시 샘플 검증한다.
- [ ] `heading_path`가 비어 있지 않다.

---

### 1.3 NO_CONTEXT 처리

**문제:** 질문이 해당 버전 문서 범위를 벗어날 때 LLM이 훈련 데이터 기반으로 잘못된 답변을 생성할 수 있다.

**동작 방식:**

1. Retriever가 반환한 k개 청크 중 최대 유사도 점수 `max_similarity`를 확인한다.
2. `max_similarity < τ` 이면 LLM을 호출하지 않는다.
3. SSE로 아래 이벤트 순서를 반환한다:

```
event: meta
data: {"noContext": true, "sources": []}

event: done
data: {"status": "NO_CONTEXT"}
```

**임계값 τ 결정:**
- E1 실험 프로토콜(`claude/protocol.md` §E1)에 따라 Q-oos 질문셋으로 FPR ≤ 5% 조건에서 τ를 결정한다.
- τ는 `configs/retriever.yaml`에 버전별로 기록한다.

**인수 기준 (RAG-06):**
- [ ] `max_similarity < τ` 인 Q-oos 질문 10개에 대해 모두 `NO_CONTEXT` SSE 응답을 반환한다.
- [ ] `NO_CONTEXT` 반환 시 LLM API 호출 흔적이 없다 (로그 검증).
- [ ] `meta` 이벤트의 `noContext: true`, `sources: []`가 포함되고, `done` 이벤트의 `status: "NO_CONTEXT"`가 반환된다.

---

### 1.4 멀티턴 대화 (질의 재작성)

**문제:** 사용자가 이전 대화를 참고하는 추가 질문("그럼 거기서 async는 어떻게 써?")을 입력하면, 질문만으로는 검색 키워드가 부족해 Retriever 성능이 저하된다.

**동작 방식:**

1. `conversation_id`가 전달되면 최근 N턴 대화 이력을 PostgreSQL에서 조회한다.
2. LLM에 대화 이력 + 현재 질문을 전달하여 **독립형 검색 질의(standalone query)** 를 생성한다.
3. 재작성된 질의로 Retriever를 호출한다.
4. 대화 이력이 없으면 (1.1)과 동일한 흐름으로 처리한다.

**입력 추가 필드:**

| 필드 | 설명 |
| --- | --- |
| `conversation_id` | 기존 대화 ID |
| `message_id` | 이전 메시지 ID (선택) |

**인수 기준 (RAG-08, HIST-01):**
- [ ] 2턴 이상 대화에서 "그 메서드의 반환 타입은?" 형태의 대명사 질문이 올바른 청크를 검색한다.
- [ ] 대화 이력 조회 실패 시 멀티턴 없이 단일 질문으로 fallback한다.
- [ ] `conversation`, `message`, `source` 테이블에 각 턴이 정상 저장된다.

---

### 1.5 버전 비교 모드

**문제:** v0.3과 v1.x의 동일한 기능이 어떻게 달라졌는지를 한 화면에서 비교하기 어렵다.

**동작 방식:**

1. 사용자가 "비교 모드"를 활성화하고 질문을 입력한다.
2. ai-server가 v0.3·v1.x 컬렉션에 **동시에** 검색 요청을 보낸다 (`asyncio.gather`).
3. 두 컨텍스트를 하나의 OpenAI **Structured Outputs** 요청으로 비스트리밍 호출한다. JSON 스키마로 `answerA`·`answerB` 필드를 강제한다.
4. 결과를 검증 후 `meta → done` 이벤트 2회로 반환한다. **token 이벤트 없음.**
5. 프론트엔드는 `done.compareResult`를 받아 좌/우 패널로 렌더링한다.

**출력 (SSE 이벤트 순서):**

```
event: meta
data: {"mode": "COMPARE", "sources": {"langchain_v03": [...], "langchain_v1x": [...]}}

event: done
data: {
  "status": "OK",
  "compareResult": {
    "answerA": "v0.3에서는 AgentExecutor.from_agent_and_tools(...)를 사용합니다.",
    "answerB": "v1.x에서는 create_react_agent(llm, tools, prompt)를 사용합니다."
  }
}
```

**성능 요건:** Structured Outputs 비스트리밍 호출이므로 TTFT 개념 없음. 전체 응답 완료 p95 ≤ 30초.

**인수 기준 (RAG-09):**
- [ ] `meta` 이벤트가 먼저 도달하고 `done` 이벤트가 뒤따른다. token 이벤트는 발생하지 않는다.
- [ ] `done.compareResult.answerA`와 `answerB` 모두 비어 있지 않다.
- [ ] 한 쪽이 NO_CONTEXT 범위이면 해당 answer 필드에 "관련 내용 없음" 메시지가 포함된다.
- [ ] OpenAI Structured Outputs JSON 스키마 검증을 통과한다.

---

### 1.6 오프라인 인덱스 빌드 및 활성화

**문제:** 프로덕션 서버에서 임베딩을 실행하면 EC2 t3.small 메모리를 초과하고, 빌드 중 서비스가 중단된다.

**동작 방식:**

1. 로컬 환경에서 `scripts/build_index.py` 를 실행한다.
2. 전처리된 `chunks.jsonl`을 읽고 `text-embedding-3-small`로 임베딩한다.
3. Chroma PersistentClient로 `langchain_{source_key}_run{id}` 컬렉션에 저장한다.
4. `chroma_data/` 디렉터리를 `tar.gz`로 압축하고 EC2에 `rsync`로 전송한다.
5. 인덱스 빌드가 VALIDATING → READY 상태에 도달하면, 관리자가 **검토 후** `make activate-index`를 실행하여 DB의 ingest_run을 ACTIVE로 직접 전환한다.
6. `POST /internal/v1/index/reload` 를 호출하여 ai-server 인메모리 캐시를 무효화하고 새 ACTIVE 인덱스를 로드한다.
7. 이전 컬렉션은 24시간 유지 후 SUPERSEDED → PURGED (롤백 여유).

**인수 기준 (RAG-10, RAG-11, RAG-12):**
- [ ] 스냅샷 복원 후 인덱스 활성화 완료까지 서비스 다운타임이 0초다 (HTTP 200 유지 검증).
- [ ] `make activate-index` → `POST /internal/v1/index/reload` 완료 후 첫 번째 쿼리가 새 컬렉션에서 처리된다.
- [ ] `symbol_validator.py`가 무효 permalink(404)를 샘플에서 1% 이상 발견하면 빌드를 중단한다 (P2).

---

### 1.7 JWT 인증 및 익명 세션

**문제:** 무제한 API 호출을 허용하면 비용이 통제되지 않는다. 비회원도 서비스를 체험할 수 있어야 한다.

**동작 방식:**

1. **익명 세션:** 로그인 없이 세션 쿠키로 최대 5회 질문을 허용한다. 5회 초과 시 로그인을 요구한다.
2. **JWT 인증:** 로그인 성공 시 Access Token(30분) + Refresh Token(7일)을 발급한다.
3. **Refresh 로테이션:** Access Token 만료 시 Refresh Token을 교체 발급하고 이전 Refresh Token을 폐기한다.
4. **재사용 탐지:** 폐기된 Refresh Token 재사용 시 해당 사용자의 모든 Refresh Token을 폐기한다.
5. **일일 쿼터:** 로그인 사용자는 하루 100회 질문 제한. 초과 시 429 응답.

**인수 기준 (AUTH-01, AUTH-02, AUTH-03):**
- [ ] 익명 세션 5회 초과 시 429 응답(`GUEST_QUOTA_EXCEEDED`)과 로그인 안내 메시지를 반환한다.
- [ ] 폐기된 Refresh Token 재사용 시 409 Conflict와 함께 전체 토큰 폐기가 발생한다.
- [ ] 일일 100회 초과 시 429 Too Many Requests 응답을 반환한다.
- [ ] bcrypt(cost **10**)로 비밀번호가 저장된다.

---

### 1.8 대화 이력 조회

**문제:** 과거 질문과 답변을 다시 보거나 대화를 이어서 진행하고 싶다.

**동작 방식:**

1. `GET /api/v1/conversations` : 사용자의 대화 목록을 최신순으로 반환한다.
2. `GET /api/v1/conversations/{id}` : 특정 대화의 메시지와 출처 목록을 반환한다.
3. 이어서 질문 시 `conversation_id`를 포함한 채 (1.4) 흐름을 타면 된다.

**인수 기준 (HIST-01, HIST-02):**
- [ ] 로그인 사용자가 질문한 모든 대화가 목록에 포함된다.
- [ ] 익명 세션의 대화는 세션 만료 후 목록에서 보이지 않는다.
- [ ] 타 사용자의 대화 ID로 조회 시 403 Forbidden을 반환한다.

---

### 1.9 관리자 인덱스 관리

**문제:** 새 버전의 LangChain 문서가 릴리즈되거나 청킹 전략을 바꿀 때 인덱스를 갱신해야 한다.

**동작 방식:**

1. 관리자 계정(`role=ADMIN`)만 `/api/v1/admin/*` 경로에 접근 가능하다.
2. `GET /api/v1/admin/index/status` : 현재 활성 ingest_run ID, 문서 수, 마지막 빌드 시각을 반환한다.
3. `POST /api/v1/admin/index/ingest/{sourceKey}` : 파이프라인 재수집을 트리거한다. 백엔드가 ingest_run을 생성하고 ai-server 파이프라인을 호출한다.
4. READY 상태 도달 후 관리자가 `make activate-index`로 활성화하고, `POST /internal/v1/index/reload`로 ai-server 캐시를 갱신한다.

**인수 기준 (ADM-01, ADM-02):**
- [ ] `role=USER` 계정으로 `/api/v1/admin/*` 호출 시 403 Forbidden을 반환한다.
- [ ] `make activate-index` + `/internal/v1/index/reload` 완료 후 `GET /api/v1/admin/index/status`의 `active_run_id`가 갱신된다.

---

## 2. 요구사항 정의

### 2.1 기능 요구사항

| ID | 기능 | 설명 | 담당 | 우선순위 |
| --- | --- | --- | --- | --- |
| RAG-01 | Source Adapter | source_key별 Chroma 컬렉션 차이를 추상화하여 `NormalizedDocument` 스키마로 통일 반환 | AI-SVC | P0 |
| RAG-02 | SHA-fixed 컬렉션 | 인덱스 빌드 시 커밋 SHA를 컬렉션 메타데이터에 기록. 재현 가능한 검색 결과 보장 | AI-SVC | P0 |
| RAG-03 | 문서 전처리 | frontmatter 제거, JSX 태그 제거, 노트북 직렬화, snippet expansion (v1.x), 헤딩 단위 청크 분할 | AI-SVC | P0 |
| RAG-04 | 버전 격리 벡터 검색 | 쿼리 source_key와 일치하는 컬렉션에서만 검색. 다른 버전 청크가 결과에 포함되지 않음 | AI-SVC | P0 |
| RAG-05 | 출처 반환 | `heading_path` + SHA-고정 `permalink` 를 `meta` 이벤트로 답변 전에 전송 | AI-SVC | P0 |
| RAG-06 | NO_CONTEXT | 최대 유사도 < τ 시 LLM 미호출, `meta(noContext=true)→done(NO_CONTEXT)` SSE 반환 | AI-SVC | P0 |
| RAG-07 | SSE 스트리밍 | SINGLE 모드: `meta` → `token*` → `done` 순서로 청크 단위 스트리밍 | AI-SVC | P0 |
| RAG-08 | 멀티턴 질의 재작성 | 대화 이력 기반 standalone query 생성 후 재검색 | AI-SVC | P1 |
| RAG-09 | 버전 비교 모드 | v0.3·v1.x 동시 검색 후 Structured Outputs 비스트리밍 호출, `compareResult` JSON 반환 | AI-SVC | P1 |
| RAG-10 | 인덱스 상태 조회 | `GET /api/v1/admin/index/status`: 활성 run ID, 문서 수, 빌드 시각 | AI-BE | P1 |
| RAG-11 | 스냅샷 복원 | EC2 rsync + Chroma 마운트로 다운타임 없이 컬렉션 교체 | AI-SVC | P1 |
| RAG-12 | 심볼 검증기 | permalink 404 비율 ≥ 1% 시 빌드 중단 | AI-SVC | P2 |
| AUTH-01 | JWT 인증 | Access 30분 + Refresh 7일, 로테이션, 재사용 탐지 | AI-BE | P0 |
| AUTH-02 | 익명 세션 제한 | 비로그인 5회 질문 후 로그인 요구 | AI-BE | P0 |
| AUTH-03 | 관리자 역할 분리 | `role=ADMIN` 만 `/api/v1/admin/*` 접근 허용 | AI-BE | P0 |
| AUTH-04 | 일일 쿼터 100 | 로그인 사용자 하루 100회 초과 시 429 | AI-BE | P1 |
| HIST-01 | 대화·메시지·출처 저장 | PostgreSQL `conversation`, `message`, `source` 테이블 | AI-BE | P1 |
| HIST-02 | 이력 조회·계속하기 | 목록·상세 API, 이어서 질문 시 `conversation_id` 연결 | AI-BE | P1 |
| ADM-01 | 인덱스 상태 대시보드 | 활성 컬렉션 ID, 문서 수, 마지막 빌드 시각 조회 | AI-BE | P1 |
| ADM-02 | 재수집 트리거 | `POST /api/v1/admin/index/ingest/{sourceKey}`: 파이프라인 재수집 시작 | AI-BE | P2 |
| UI-01 | 버전·모드 선택 | `/api/meta` 응답 기반으로 프론트가 버전·비교 모드 렌더링 | FRONT | P0 |
| UI-02 | 출처 카드 + 스트리밍 렌더 | `meta` 이벤트 → 출처 카드 선렌더, `token` 이벤트 → 텍스트 스트림 | FRONT | P0 |
| UI-03 | 비교 뷰 | 좌/우 패널, `compareResult` 기반 렌더링 | FRONT | P1 |
| UI-04 | k6 mock 모드 | 로드 테스트 시 LLM 없이 고정 응답 반환 (`X-Mock-LLM: true` 헤더) | AI-SVC | P2 |

### 2.2 비기능 요구사항

| ID | 항목 | 목표 |
| --- | --- | --- |
| NFR-P1 | TTFT (단일 모드) | EC2 t3.small에서 p95 ≤ 3초 (E5 실험) |
| NFR-P2 | Retriever 지연 | p95 ≤ 500ms (8.3-1) |
| NFR-P3 | EmbeddingClient 지연 | p95 ≤ 200ms (8.3-2) |
| NFR-P4 | 비교 모드 응답 완료 | Structured Outputs 비스트리밍 p95 ≤ 30초 |
| NFR-P5 | 동시 스트림 | 50 동시 연결에서 에러율 1% 미만 (E6 k6) |
| NFR-R1 | 버전 격리 | v0.3 질문에 v1.x 청크가 1건도 포함되지 않음 |
| NFR-R2 | 무중단 인덱스 갱신 | 스냅샷 교체 중 HTTP 200 유지 |
| NFR-R3 | 2시간 소크 | 에러율 증가 없음 |
| NFR-Q1 | Permalink 유효성 | 활성 컬렉션 permalink 404 비율 < 1% |
| NFR-Q2 | 청킹 증거 | E2 선택 근거 `eval/decision_rules.md` 커밋 |
| NFR-O1 | 메모리 예산 | t3.small 2GB, Chroma ≤ 800MB, FastAPI ≤ 400MB, Spring Boot ≤ 400MB |
| NFR-C1 | CI/CD | PR 시 단위·통합 테스트 자동 실행, 실패 시 머지 차단 |

### 2.3 정책 및 제약

| 항목 | 내용 |
| --- | --- |
| 프로덕션 임베딩 금지 | EC2에서 `build_index.py` 실행 불가. 스냅샷 복원만 허용 |
| 외부 ML 데이터셋 없음 | 모델 fine-tuning 없음. 모든 지식은 RAG 컨텍스트로 주입 |
| 서비스 언어 | 질문·답변은 한국어·영어 모두 지원. 평가 질문셋은 한국어 |
| LLM 모델 고정 | GPT-4o-mini, temperature=0 |
| 임베딩 모델 고정 | `text-embedding-3-small` |

---

## 3. MVP 범위

| Sprint | 완료 기준 |
| --- | --- |
| **SP1** (핵심 RAG) | RAG-01~07, AUTH-01~02, UI-01~02 완료. 단일 버전 RAG 질의응답 E2E 동작 |
| **SP2** (확장 기능) | RAG-08~11, AUTH-03~04, HIST-01~02, ADM-01, UI-03 완료. 멀티턴·비교 모드·이력 조회 E2E 동작 |
| **P2 (백로그)** | RAG-12, ADM-02, UI-04 |

**SP1 인수 체크리스트:**
- [ ] SP1-01 버전 선택 RAG 질의응답 E2E (브라우저에서 SSE 수신 확인)
- [ ] SP1-02 NO_CONTEXT SSE 반환 (Q-oos 질문 1건 수동 테스트, `meta.noContext=true` + `done.status=NO_CONTEXT` 확인)
- [ ] SP1-03 `meta` 이벤트 출처 카드 렌더링
- [ ] SP1-04 JWT 로그인 → 질문 → 로그아웃 E2E
- [ ] SP1-05 익명 5회 초과 시 로그인 요구

**SP2 인수 체크리스트:**
- [ ] SP2-01 멀티턴 대화에서 대명사 질문이 올바른 청크 검색
- [ ] SP2-02 비교 모드 `compareResult` 반환 및 좌/우 패널 UI 렌더링 확인
- [ ] SP2-03 대화 이력 목록·상세 조회
- [ ] SP2-04 `/api/v1/admin/index/status` 조회 및 인덱스 활성화 흐름 동작
- [ ] SP2-05 일일 100회 쿼터 초과 시 429 응답

---

## 4. 설계 방어 포인트

이 섹션은 졸업 발표·심사에서 예상되는 질문과 답변을 정리한 것이다.

**Q1. Chroma를 선택한 이유는? pgvector 대비 장단점은?**

Chroma는 Python-native PersistentClient로 설치 없이 프로세스 내 임베딩이 가능하다. t3.small 단일 서버 환경에서 추가 프로세스(pgvector daemon)를 띄우지 않아도 되며 메모리 예산을 절약한다. 대신 Chroma는 수평 확장이 어렵고, 버전별 격리를 위해 컬렉션을 별도 관리해야 한다. 졸업 작품 규모(문서 수 수천 건)에서 pgvector의 SQL 연동 이점보다 운영 단순성이 더 중요하다고 판단했다.

**Q2. 왜 프로덕션에서 임베딩을 실행하지 않는가?**

`text-embedding-3-small` 임베딩은 수천 건 문서에 대해 수 분이 소요되며 OpenAI API 비용이 발생한다. 더 중요하게는, 임베딩 중 Chroma 쓰기 잠금으로 검색 쿼리 응답이 지연된다. 오프라인 빌드 + 스냅샷 rsync 방식을 선택하면 프로덕션 다운타임 없이 인덱스를 교체할 수 있고, t3.small의 2GB 메모리 제약 내에서 안정적으로 운영된다.

**Q3. 버전 오염 문제를 어떻게 해결했는가?**

3계층으로 분리했다. L1(소스): 버전별 별개 GitHub 저장소/브랜치에서 sparse checkout. L2(검색): 버전별 별개 Chroma 컬렉션. L3(생성): 시스템 프롬프트에 버전 명시 + NO_CONTEXT로 범위 외 질문 차단. E1 실험에서 세 조건(비격리 / 필터만 / 컬렉션 분리)을 측정하여 L2 격리의 효과를 수치로 검증한다.

**Q4. NO_CONTEXT 임계값 τ를 어떻게 결정했는가?**

Q-oos 질문셋(버전 범위 밖 주제 10문항)으로 FPR(정상 질문을 NO_CONTEXT로 오분류하는 비율) ≤ 5% 조건에서 precision-recall 커브를 그려 τ를 선택한다. τ가 낮으면 범위 밖 질문에도 LLM이 응답하고, τ가 너무 높으면 정상 질문도 차단된다. 버전별로 임베딩 분포가 다르므로 `configs/retriever.yaml`에 `tau_v03`, `tau_v1x`를 별도로 기록한다.

**Q5. 비교 모드에서 왜 SSE 스트리밍 대신 Structured Outputs를 사용하는가?**

두 버전의 답변을 각각 스트리밍하면 클라이언트가 채널별 토큰을 인터리빙해야 하고, 한 채널이 먼저 끝났을 때 UI 처리가 복잡해진다. Structured Outputs는 JSON 스키마로 `answerA`·`answerB` 필드를 보장하므로 파싱 없이 바로 렌더링할 수 있고, 형식 오류 없이 두 답변이 함께 완성되는 원자성을 얻는다. 비교 모드는 사용자가 버전 차이를 대조하는 것이 목적이므로 TTFT보다 답변 일관성이 더 중요하다.

**Q6. 멀티턴 질의 재작성이 왜 필요한가? 그냥 대화 이력을 붙이면 안 되는가?**

대화 이력 전체를 임베딩 쿼리로 쓰면 1,000자 제한을 초과하거나 이전 대화의 노이즈가 쿼리 벡터를 희석시킨다. standalone query 재작성은 현재 질문의 의미를 압축하여 Retriever가 가장 관련성 높은 청크를 찾게 한다. 추가 LLM 호출 비용이 발생하지만, Retriever recall 향상이 더 크다.

**Q7. EC2 t3.small 메모리 2GB 내에서 어떻게 운영하는가?**

메모리 예산: Chroma ≤ 800MB (두 컬렉션 합산), FastAPI ≤ 400MB, Spring Boot ≤ 400MB, 여유 ≈ 400MB. Chroma는 PersistentClient이므로 디스크 기반 접근이고, 쿼리 시에만 인덱스 일부를 메모리에 로드한다. Spring Boot는 `-Xmx300m` JVM 옵션으로 제한한다. 임베딩 모델은 로컬에서 돌리지 않고 OpenAI API를 호출하므로 메모리 사용이 없다.

---

## 미결 사항

- [ ] **S-1** RAG-08 멀티턴 재작성에 쓸 LLM 모델 확정 (GPT-4o-mini vs GPT-3.5-turbo 비용 비교)
- [ ] **S-2** AUTH-04 일일 쿼터 초기화 주기 확정 (UTC 00:00 vs 로그인 기준 24시간)
- [ ] **S-3** HIST-01 대화 보존 기간 정책 확정 (익명 세션: 세션 만료 시 / 로그인: 무기한)
- [ ] **S-4** NFR-P5 k6 50 VU 시나리오에서 mock LLM 고정 응답 지연 설정값 확정 (E6 준비)
- [ ] **S-5** UI-02 출처 카드 클릭 시 GitHub permalink 새 탭 오픈 여부 (UX 결정)

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
| --- | --- | --- |
| v0.1 | 2026-11-04 | 최초 작성 |
| v0.2 | 2026-11-05 | §1.3 NO_CONTEXT SSE 계약으로 수정, §1.5 비교 모드 Structured Outputs로 재작성, §1.6 activate flow 수정(make activate-index + internal/reload), §1.7 bcrypt cost 12→10, §1.8 경로 /api/v1/conversations 수정, §1.9 admin API 경로 수정, §2.1 RAG-09/ADM-02 설명 갱신, §2.3 seed=42 제거, SP2 체크리스트 갱신 |
| v0.3 | 2026-11-06 | §1.7 익명 세션 초과 응답 코드 401 → 429(`GUEST_QUOTA_EXCEEDED`) 수정 |

---

end.
