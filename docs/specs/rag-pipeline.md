# RAG 파이프라인 설계

> **최종 수정**: 2026-11-18

---

## 1. 개요

- **목적**: FastAPI ai-server 내 RAG 쿼리 처리 파이프라인의 전체 흐름, 컴포넌트 책임, 데이터 흐름을 정의한다.
- **범위**: 단일 버전 RAG, 멀티턴 질의 재작성, 버전 비교 모드, NO_CONTEXT 판정을 모두 포함한다. 인덱스 빌드 파이프라인은 `docs/specs/data-sources.md`·`docs/specs/doc-source.md`를 참조한다.
- **관련 문서**: `docs/specs/interfaces.md` (Protocol 정의), `docs/specs/api-spec.md` §6·부록 B (HTTP·SSE 계약), `docs/specs/data-sources.md` (컬렉션 빌드 절차)

---

## 2. 파이프라인 개요

### 2.1 단일 버전 RAG 흐름

```
backend (POST /api/v1/chat/stream 중계)
  │  POST /internal/v1/chat/stream  (requestId, mode=SINGLE, sourceKey, question, history, promptVersion)
  │  X-Internal-Token (ADR-012)
  ▼
[FastAPI Router]  검증 · ACTIVE run 확정 · 동시성 슬롯 (실패는 HTTP 상태, api-spec §6.1)
  │
  ├─ history 있음?
  │   ├─ YES → [1. 질의 재작성]  ← backend가 보낸 최근 3턴 (멀티턴, R-7-2)
  │   └─ NO  → 원본 질문 사용
  │
  ▼
[2. 임베딩]  EmbeddingClient → text-embedding-3-small
  │
  ▼
[3. 벡터 검색]  Chroma {source_key}_run{active_run_id}  top_k=8 (rag.yaml, E2)  + 2차 메타데이터 검증(INV-02)
  │
  ├─ max_similarity < τ?
  │   └─ YES → [NO_CONTEXT 응답]  LLM 미호출, SSE meta→done 반환
  │
  ▼
[4. 컨텍스트 선택]  similarity ≥ τ 청크, 3,000토큰 예산 (RetrievedChunk 그대로)
  │
  ▼
[5. 프롬프트 조립]  system(규칙 + 번호 붙은 참고 문서) + question
  │
  ▼
[6. LLM 스트리밍]  GPT-4o-mini, temperature=0
  │
  ▼
SSE Stream  (계약: contracts/sse-events.schema.json · API 명세 부록 B)
  event: meta   → {"event": "meta", "requestId": "...", "sourceKey": "langchain_v03", "noContext": false, "sources": [...]}
  event: token  → {"event": "token", "t": "..."} (반복)
  event: done   → {"event": "done", "status": "COMPLETED", "finishReason": "stop", ...}
```

### 2.2 버전 비교 모드 흐름

COMPARE 모드는 SSE 스트리밍이 **아니다**. OpenAI Structured Outputs 비스트리밍 단일 호출로 두 버전의 답변을 원자적으로 반환한다. token 이벤트는 발생하지 않는다.

```
Client
  │  POST /internal/v1/chat/stream  (mode=COMPARE, sourceKeyA, sourceKeyB, question)
  ▼
[FastAPI Router]
  │
  ├─ asyncio.gather(
  │     retrieve(source_key=source_key_a, question),
  │     retrieve(source_key=source_key_b, question)
  │  )  ← 두 컬렉션 동시 검색
  │
  ▼
[Structured Outputs 비스트리밍 호출]
  OpenAI gpt-4o-mini, response_format=CompareResult
  (두 컨텍스트 + 질문 → version_a · version_b · changes 생성, 정책서 §5.6)
  │
  ▼
SSE Stream (token 이벤트 없음)
  event: meta   → {"event": "meta", "sourceKeyA": "langchain_v03", "sourceKeyB": "langchain_v1x", "sources": [{"rank": "A1", ...}, {"rank": "B1", ...}], ...}
  event: done   → {"event": "done", "status": "COMPLETED", "compareResult": {"version_a": {...}, "version_b": {...}, "changes": [...]}}
```

---

## 3. 컴포넌트별 상세

### 3.1 단계 1 — 질의 재작성 (멀티턴 전용)

| 항목 | 값 |
| --- | --- |
| **입력** | `question` (현재 턴), `history` (backend·게스트 화면이 고른 최근 3턴, 실패·근거 부족 답변 제외) |
| **출력** | 검색 질의, `rewritten_query: str \| None`, `rewrite_status` (`OK`·`FALLBACK`·`SKIPPED`), `rewrite_ms` |
| **호출 조건** | `history`가 비어 있지 않을 때. 비었으면 `SKIPPED`(원본 질문 사용, LLM 미호출) |
| **N턴 기본값** | 최근 3턴(6메시지), 이전 assistant는 앞 500자 (설정: `configs/rag.yaml → rewrite`) |
| **프롬프트** | `configs/prompts/rewrite_v1.j2` (`rewrite.prompt_version`), 템플릿 하나를 user 메시지로 보낸다 |
| **LLM 모델** | `configs/models.yaml → rewrite` (gpt-4o-mini, temperature 0, 비스트리밍, 재시도 없음) |

**프롬프트 구조:**

```
system:
  당신은 대화 이력을 보고 사용자의 현재 질문을 독립형 검색 쿼리로 재작성하는 도우미입니다.
  - 대명사나 지시어를 명시적 단어로 교체하세요.
  - 불필요한 맥락은 제거하고 검색에 적합한 한 문장으로 만드세요.
  - 원본 질문이 이미 독립적이면 그대로 반환하세요.

user:
  [대화 이력]
  사용자: {turn_1_question}
  AI: {turn_1_answer_summary}
  사용자: {turn_2_question}
  AI: {turn_2_answer_summary}

  [현재 질문]
  {current_question}

  독립형 검색 쿼리를 한 문장으로 반환하세요.
```

**폴백:** 3초 초과·빈 출력·200자 초과·호출 오류면 원본 `question`을 그대로 검색에 쓰고 `FALLBACK`으로 기록한다(정책서 §5.2). 에러를 호출자에게 전파하지 않는다.

**사용 범위:** 재작성 질의는 검색(임베딩)에만 쓴다. 생성 프롬프트에는 원본 질문을 넣는다(ADR-009).

---

### 3.2 단계 2 — 임베딩

| 항목 | 값 |
| --- | --- |
| **구현체** | `OpenAIEmbeddingClient` |
| **모델** | `text-embedding-3-small` |
| **입력** | `rewritten_query` (또는 원본 `question`) |
| **출력** | `query_vector: list[float]` (1536차원) |
| **p95 목표** | 200ms (8.3-2) |

**에러 처리:** 질의 임베딩은 5초 제한·재시도 1회(정책서 §2.1). 그래도 실패하면 스트림 시작 후이므로 HTTP 상태가 아니라 `error` 이벤트(`LLM_ERROR`, `partial=false`)로 끝낸다 (INV-09, api-spec §6.1).

---

### 3.3 단계 3 — 벡터 검색

| 항목 | 값 |
| --- | --- |
| **구현체** | `ChromaRetriever` |
| **컬렉션** | `{source_key}_run{active_run_id}` (ADR-004) |
| **검색 방식** | cosine similarity |
| **반환 수 k** | 5 (설정: `configs/rag.yaml → retrieval.top_k`) |
| **버전 격리** | 1차: ACTIVE run 컬렉션 하나만 지정 (`where` 필터 미사용). 2차: 결과 청크의 `source_key`·`version`·`ingest_run_id`가 다르면 폐기 + ERROR 로그 (INV-02, ADR-004) |
| **임베딩 모델 검사** | 컬렉션·청크의 `embedding_model` ≠ 질의 모델이면 검색 거부 (INV-03, `EMBEDDING_MODEL_MISMATCH`) |
| **p95 목표** | 500ms (임베딩 포함, 8.3-1) |

**컬렉션 조회 순서:**

```python
# 활성 포인터에서 run id를 조회 (30초 캐시)
active_run_id = db.query_active_run_id(source_key)   # ai.index_pointers WHERE source_key=?
collection_name = f"{source_key}_run{active_run_id}"
# source_key: "langchain_v03" | "langchain_v1x"
```

**NO_CONTEXT 판정:**

```python
chunks = retriever.retrieve(query=rewritten_query, source_key=source_key, top_k=k)
max_similarity = max((c.similarity for c in chunks), default=0.0)
τ = load_tau(source_key)   # configs/rag.yaml → retrieval.thresholds.{source_key}, TAU_{SOURCE_KEY}로 덮어쓰기

if max_similarity < τ:
    return NO_CONTEXT_RESPONSE   # SSE: meta(noContext=true) → done(NO_CONTEXT)
```

---

### 3.4 단계 4 — 컨텍스트 선택

| 항목 | 값 |
| --- | --- |
| **입력** | `list[RetrievedChunk]` (similarity 내림차순, `interfaces.md` §2.1) |
| **출력** | 컨텍스트 청크 목록 — 순서가 인용 번호 `[1..n]`이자 SSE meta.sources rank |
| **규칙** | similarity ≥ τ 청크만, 최대 3,000토큰, 초과 시 낮은 rank부터 제외 (정책서 §5.3) |

- 질의 단계에는 Source Adapter가 없다. Adapter는 인덱스 빌드에서 원문을 `NormalizedDocument`로 바꾸는 데만 쓴다(ADR-006). 검색 결과는 Chroma 메타데이터(`heading_path`·`permalink`·`site_url` 등, 정책서 §4.2)를 그대로 담은 `RetrievedChunk`다.
- 상세 파싱 규칙(인덱스 빌드)은 `docs/specs/doc-source.md`를 참조한다.

---

### 3.5 단계 5 — 프롬프트 조립

**시스템 프롬프트 템플릿** (`configs/prompts/{prompt_version}.j2`, 현재 `single_v2.j2`):

- 파일명(확장자 제외)이 `prompt_version`이다. 문구를 바꿀 때는 기존 파일을 고치지 않고 새 버전 파일을 추가한다 (정책서 §5.5).
- 규칙은 정책서 §5.5 다섯 가지다: ① 컨텍스트 밖 지식으로 API·코드를 만들지 않는다 ② 주장마다 `[n]` 인용 ③ 선택 버전을 답변 첫 줄에 명시 ④ 코드 예시는 컨텍스트 코드에 근거 ⑤ 근거가 부족하면 기준 버전 줄 없이 `[[NO_ANSWER]]`만 출력(③보다 우선).
- 버전 이력: `single_v1` → `single_v2`(#108) — v1은 ③과 ⑤의 우선순위가 없어 모델이 `LangChain v1.x 기준 [[NO_ANSWER]]`처럼 머리말 뒤에 sentinel을 써 판정을 빠져나갔다. v2는 ⑤가 ③보다 우선임을 명시한다. sentinel 판정 규칙은 정책서 §5.4.
- 답변은 한국어, API명·코드·에러 메시지는 원문 유지 (정책서 §5.1).
- 템플릿 변수: `display_name`(예: LangChain v1.x), `documents[]`(`rank`·`heading_path`·`file_path`·`content`). `rank`가 인용 번호이며 SSE meta.sources rank와 같다.
- 메시지: system = 규칙 + 번호 붙은 [참고 문서], user = 질문 원문. 단일 모드 R-4 범위에서는 대화 이력을 생성 메시지에 넣지 않는다(멀티턴은 질의 재작성으로 처리, §3.1).

**멀티턴 메시지 조립:**

```python
messages = [{"role": "system", "content": system_prompt}]

# 대화 이력 (최근 N턴)
for turn in history[-N:]:
    messages.append({"role": "user",      "content": turn.question})
    messages.append({"role": "assistant", "content": turn.answer_summary})

# 현재 질문
messages.append({"role": "user", "content": current_question})
```

**컨텍스트 토큰 예산:** 정책서 §5.3을 따른다 — similarity ≥ τ 청크만, 최대 3,000토큰(`configs/rag.yaml` `retrieval.context_budget_tokens`), 초과 시 낮은 rank부터 제외, 청크 중간 절단 금지. 토큰 수는 청크 메타데이터 `token_count`(tiktoken).

---

### 3.6 단계 6 — LLM 스트리밍 (SINGLE 모드 전용)

> **SINGLE 모드 전용.** COMPARE 모드는 §5의 Structured Outputs 비스트리밍 흐름을 사용한다.

| 항목 | 값 |
| --- | --- |
| **모델** | `gpt-4o-mini` |
| **temperature** | `0` |
| **stream** | `True` |
| **max_tokens** | `1024` (설정: `configs/models.yaml` `llm`) |
| **첫 토큰 타임아웃** | 10초, 재시도 없음 (정책서 §2.1) |
| **모델 선택** | `LLM_MODEL` 환경 변수 → 없으면 `configs/models.yaml` `llm.model` |
| **구현체** | `OpenAIAnswerGenerator.generate_stream()` |

**SSE 이벤트 발행 순서 (SINGLE 모드):**

```python
# 1. meta 이벤트 — LLM 호출 전에 먼저 전송
# 필드 표기는 계약(contracts/sse-events.schema.json)을 따른다 — camelCase
yield SseEvent(event="meta", data={
    "requestId": request_id,
    "sourceKey": source_key,
    "noContext": False,
    # rank·headingPath·permalink·siteUrl·similarity
    "sources": [to_source_payload(rank, doc) for rank, doc in enumerate(normalized_docs, 1)],
})

# 2. token 이벤트 — LLM 스트림에서 수신 즉시 전송
async for chunk in llm_stream:
    text = chunk.choices[0].delta.content or ""
    if text:
        yield SseEvent(event="token", data={"t": text})

# 3. done 이벤트
yield SseEvent(event="done", data={"status": "COMPLETED", "finishReason": "stop"})
```

**클라이언트 연결 끊김 처리:**
- `asyncio.CancelledError` 감지 시 LLM 스트림 즉시 종료
- OpenAI SDK의 `response.close()` 호출로 HTTP 연결 해제
- 로그에 `stream_aborted` 기록 (토큰 과금 최소화 목적)

---

## 4. NO_CONTEXT 응답 형식

LLM을 호출하지 않고 SSE 이벤트 2개로 반환한다. 단일 JSON HTTP 응답이 **아니다**.

```
event: meta
data: {"noContext": true, "sources": []}

event: done
data: {"status": "NO_CONTEXT", "statusReason": "LOW_SIMILARITY"}
```

> 예시는 핵심 필드만 적었다. `requestId` 등 필수 필드는 계약(`contracts/sse-events.schema.json`)을 따른다.

**구현:**

```python
async def _yield_no_context() -> AsyncIterator[SseEvent]:
    yield SseEvent(event="meta", data={"noContext": True, "sources": []})
    yield SseEvent(event="done", data={"status": "NO_CONTEXT", "statusReason": "LOW_SIMILARITY"})
```

> `max_similarity`·`threshold`는 서버 측 로그(`no_context_triggered` 이벤트)에만 기록한다. 클라이언트에 노출하지 않는다.

---

## 5. 비교 모드 — Structured Outputs 처리

COMPARE 모드는 asyncio queue + SSE 인터리빙 방식을 **사용하지 않는다**. OpenAI Structured Outputs로 두 버전의 답변을 단일 비스트리밍 호출로 생성한다.

```python
from pydantic import BaseModel

class CompareSide(BaseModel):
    summary: str
    citations: list[str]   # A측 A1…Ak, B측 B1…Bk
    no_evidence: bool      # 해당 측 top-1 < τ


class CompareChange(BaseModel):
    aspect: str
    a: str
    b: str
    citations_a: list[str]
    citations_b: list[str]


class CompareResult(BaseModel):
    """정책서 §5.6 비교 출력 JSON. 내부 키는 snake_case (계약 compareResult와 동일)."""
    version_a: CompareSide
    version_b: CompareSide
    changes: list[CompareChange]


async def compare_pipeline(
    question: str,
    source_key_a: str,
    source_key_b: str,
) -> AsyncIterator[SseEvent]:

    # 1. 두 소스 동시 벡터 검색
    chunks_a, chunks_b = await asyncio.gather(
        retriever.retrieve(query=question, source_key=source_key_a, top_k=retrieval.top_k),  # rag.yaml (8)
        retriever.retrieve(query=question, source_key=source_key_b, top_k=retrieval.top_k),
    )

    # 2. meta 이벤트 먼저 전송
    yield SseEvent(event="meta", data={
        "requestId": request_id,
        "sourceKeyA": source_key_a,
        "sourceKeyB": source_key_b,
        "noContext": False,
        # 출처 rank는 A측 A1…, B측 B1… (정책서 §5.6 인용 번호 체계)
        "sources": [to_source_payload(f"A{i}", c) for i, c in enumerate(chunks_a, 1)]
        + [to_source_payload(f"B{i}", c) for i, c in enumerate(chunks_b, 1)],
    })

    # 3. Structured Outputs 비스트리밍 호출 (stream=False)
    response = await openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=build_compare_messages(
            question, chunks_a, chunks_b, source_key_a, source_key_b
        ),
        response_format=CompareResult,
        temperature=0,
    )

    result: CompareResult = response.choices[0].message.parsed
    # 후처리 검증: 없는 인용 번호 제거, A·B 인용이 모두 없는 changes 항목 폐기 (정책서 §5.6)

    # 4. done 이벤트 1회 반환
    yield SseEvent(event="done", data={
        "status": "COMPLETED",
        "compareResult": result.model_dump(),
    })
```

**에러 처리:** Structured Outputs 파싱 실패(`ValidationError`)는 1회 재시도하고, 그래도 실패하면 `error` 이벤트(`COMPARE_PARSE_ERROR`)로 종결한다(정책서 §5.6·§9.2). OpenAI 호출 실패는 `LLM_ERROR`다. `done`에 오류 상태를 싣지 않는다.

```python
yield SseEvent(event="error", data={
    "code": "COMPARE_PARSE_ERROR",
    "message": "비교 결과를 만들지 못했습니다. 다시 질문해주세요.",
    "requestId": request_id,
    "partial": False,
})
```

---

## 6. 설정 파일 목록

| 파일 | 주요 설정값 |
| --- | --- |
| `configs/rag.yaml` `rewrite` | `prompt_version`, `history_turns`(3), `assistant_max_chars`(500), `max_output_chars`(200) |
| `configs/models.yaml` `rewrite` | `model`·`temperature`(0)·`max_tokens`·`timeout_seconds`(3)·`max_retries`(0) |
| `configs/ingest.yaml` | 청킹 전략 A·B·C 파라미터, 기본 전략 (인덱스 빌드 전용, `docs/specs/doc-source.md` §6) |
| `configs/rag.yaml` | `retrieval.top_k`, `retrieval.thresholds.{source_key}`(τ, ADR-008), `retrieval.context_budget_tokens` |
| `configs/models.yaml` | `llm.model`·`temperature`(0)·`max_tokens`·`first_token_timeout_seconds`·`max_retries`, `embedding.*` |
| `configs/prompts/single_v{n}.j2` | 단일 모드 시스템 프롬프트 템플릿 (파일명 = `prompt_version`) |
| `configs/prompts/compare_system.jinja2` | 비교 모드 Structured Outputs 프롬프트 |

> 모든 설정값은 하드코딩 금지. 코드에서 직접 설정값을 사용하지 않는다.
> 활성 ingest_run ID는 설정 파일이 아닌 PostgreSQL `ingest_runs` 테이블에서 조회한다.

---

## 7. 로깅 및 추적

각 요청은 UUID `request_id`로 추적한다. 아래 이벤트를 구조화 로그(JSON)로 남긴다.

| 이벤트 | 주요 필드 |
| --- | --- |
| `query_received` | `request_id`, `source_key`, `mode`, `has_history` |
| `query_rewritten` | `request_id`, `original`, `rewritten` |
| `embedding_done` | `request_id`, `latency_ms` |
| `retrieval_done` | `request_id`, `max_similarity`, `chunks_count`, `latency_ms` |
| `no_context_triggered` | `request_id`, `max_similarity`, `tau` |
| `llm_stream_start` | `request_id`, `prompt_tokens` |
| `llm_stream_done` | `request_id`, `completion_tokens`, `ttft_ms` |
| `stream_aborted` | `request_id`, `reason` |
| `compare_structured_done` | `request_id`, `latency_ms`, `answer_a_len`, `answer_b_len` |

---

## 미결 사항

- [ ] **P-1** `history_window` 기본값 최적화 (멀티턴 E2E 테스트 후 결정)
- [ ] **P-2** 비교 모드 에러 — 양쪽 소스 중 하나가 NO_CONTEXT 범위일 때 처리 방식 (해당 answer에 "관련 내용 없음" 메시지 삽입 vs 별도 플래그)
- [ ] **P-3** `configs/prompts/compare_system.jinja2` 프롬프트 최적화 (두 버전 컨텍스트를 하나의 프롬프트로 조립하는 최적 구조)
- [x] **P-4** 멀티턴 재작성 `answer_summary` 생성 방식 — 이전 답변 앞 500자 사용(정책서 §5.2, R-7-2)

---

## 변경 이력

| 버전 | 변경 내용 |
| --- | --- |
| v0.1 | 최초 작성 |
| v0.2 | §2.2 비교 모드 Structured Outputs 비스트리밍으로 재작성, §3.3 source_key로 통합(version 제거), §3.4 NormalizedDocument score→similarity/version→source_key, §3.6 seed=42 제거·channel 필드 제거·SINGLE 모드 명시, §4 NO_CONTEXT SSE로 수정, §5 asyncio queue+SSE→Structured Outputs로 전면 재작성, §6 active_collection.json 제거·seed 제거 |
| v0.3 | §2.1 다이어그램 엔드포인트 `/api/chat` → `/api/v1/chat` 수정, §2.2 다이어그램 엔드포인트 `/api/chat (mode="COMPARE")` → `/api/v1/chat/compare` + 파라미터 snake_case 통일(source_key_a·source_key_b), §5 compare_pipeline 파라미터 주석 source_key_a·source_key_b로 정렬 |
| v0.4 | §2.1 다이어그램 컬렉션 이름을 `{source_key}_run{active_run_id}`로 수정, §3.3 버전 필터(`where`) → 1차 컬렉션 지정 + 2차 메타데이터 검증·임베딩 모델 검사 (ADR-004, 정책서 §5.3) |
| v0.5 | §3.3·§6 검색 설정 파일 `configs/retriever.yaml` → `configs/rag.yaml`(ADR-008), 컨텍스트 예산 키 추가 |
| v0.6 | §3.5 프롬프트 위치 `configs/prompts/{prompt_version}.j2`·정책서 §5.5 규칙, 컨텍스트 초과 처리 → 정책서 §5.3 토큰 예산, §3.6 첫 토큰 타임아웃·모델 선택, §6 `configs/models.yaml` |
| v0.7 | §1 관련 문서 경로 정정, §2.1 진입점을 backend → `POST /internal/v1/chat/stream`으로, 4단계 Source Adapter → 컨텍스트 선택(§3.4, ADR-006), §3.2 임베딩 실패는 `error` 이벤트 |
| v0.8 | §3.5 현재 프롬프트 `single_v2`(#108) — 규칙 ⑤(근거 부족 시 sentinel만)가 ③(첫 줄 기준 버전)보다 우선 |

---

*end.*
