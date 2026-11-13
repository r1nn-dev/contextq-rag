# RAG 파이프라인 설계

> **최종 수정**: 2026-11-06

---

## 1. 개요

- **목적**: FastAPI ai-server 내 RAG 쿼리 처리 파이프라인의 전체 흐름, 컴포넌트 책임, 데이터 흐름을 정의한다.
- **범위**: 단일 버전 RAG, 멀티턴 질의 재작성, 버전 비교 모드, NO_CONTEXT 판정을 모두 포함한다. 인덱스 빌드 파이프라인은 `claude/data-sources.md`를 참조한다.
- **관련 문서**: `claude/interfaces.md` (Protocol 정의), `DevDocs-RAG API v1.md` (HTTP 계약), `claude/data-sources.md` (컬렉션 빌드 절차)

---

## 2. 파이프라인 개요

### 2.1 단일 버전 RAG 흐름

```
Client
  │  POST /api/v1/chat  (source_key, question, conversation_id?)
  ▼
[FastAPI Router]
  │
  ├─ conversation_id 있음?
  │   ├─ YES → [1. 질의 재작성]  ← PostgreSQL 대화 이력 조회
  │   └─ NO  → 원본 질문 사용
  │
  ▼
[2. 임베딩]  EmbeddingClient → text-embedding-3-small
  │
  ▼
[3. 벡터 검색]  Chroma langchain_{source_key}_run{active_id}  top_k=5
  │
  ├─ max_similarity < τ?
  │   └─ YES → [NO_CONTEXT 응답]  LLM 미호출, SSE meta→done 반환
  │
  ▼
[4. Source Adapter]  NormalizedDocument 변환
  │
  ▼
[5. 프롬프트 조립]  system + context + history + question
  │
  ▼
[6. LLM 스트리밍]  GPT-4o-mini, temperature=0
  │
  ▼
SSE Stream
  event: meta   → {"sources": [...], "source_key": "langchain_v03"}
  event: token  → {"text": "..."} (반복)
  event: done   → {"status": "OK", "finish_reason": "stop"}
```

### 2.2 버전 비교 모드 흐름

COMPARE 모드는 SSE 스트리밍이 **아니다**. OpenAI Structured Outputs 비스트리밍 단일 호출로 두 버전의 답변을 원자적으로 반환한다. token 이벤트는 발생하지 않는다.

```
Client
  │  POST /api/v1/chat/compare  (question, source_key_a, source_key_b)
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
  (두 컨텍스트 + 질문 → answerA, answerB 동시 생성)
  │
  ▼
SSE Stream (token 이벤트 없음)
  event: meta   → {"mode": "COMPARE", "sources": {"langchain_v03": [...], "langchain_v1x": [...]}}
  event: done   → {"status": "OK", "compareResult": {"answerA": "...", "answerB": "..."}}
```

---

## 3. 컴포넌트별 상세

### 3.1 단계 1 — 질의 재작성 (멀티턴 전용)

| 항목 | 값 |
| --- | --- |
| **입력** | `conversation_id`, `question` (현재 턴) |
| **출력** | `rewritten_query: str` |
| **호출 조건** | `conversation_id`가 존재하고 최근 N턴 이력이 1개 이상 있을 때 |
| **N턴 기본값** | 최근 3턴 (설정: `configs/pipeline.yaml → history_window`) |
| **LLM 모델** | GPT-4o-mini (별도 호출, temperature=0) |

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

**폴백:** 재작성 LLM 호출 실패 시 원본 `question`을 그대로 사용한다. 에러를 호출자에게 전파하지 않는다.

---

### 3.2 단계 2 — 임베딩

| 항목 | 값 |
| --- | --- |
| **구현체** | `OpenAIEmbeddingClient` |
| **모델** | `text-embedding-3-small` |
| **입력** | `rewritten_query` (또는 원본 `question`) |
| **출력** | `query_vector: list[float]` (1536차원) |
| **p95 목표** | 200ms (8.3-2) |

**에러 처리:** `EmbeddingError` 발생 시 HTTP 503 반환. 재시도는 호출자(Router) 책임.

---

### 3.3 단계 3 — 벡터 검색

| 항목 | 값 |
| --- | --- |
| **구현체** | `ChromaRetriever` |
| **컬렉션** | `langchain_{source_key}_run{active_id}` |
| **검색 방식** | cosine similarity |
| **반환 수 k** | 5 (설정: `configs/retriever.yaml → top_k`) |
| **버전 필터** | Chroma `where` 절: `{"source_key": {"$eq": "langchain_v03"}}` |
| **p95 목표** | 500ms (임베딩 포함, 8.3-1) |

**컬렉션 조회 순서:**

```python
# DB에서 ACTIVE 상태 ingest_run의 run_id를 조회
active_id = db.query_active_run_id(source_key)   # ingest_runs WHERE status='ACTIVE' AND source_key=?
collection_name = f"langchain_{source_key}_run{active_id}"
# source_key: "langchain_v03" | "langchain_v1x"
```

**NO_CONTEXT 판정:**

```python
chunks = retriever.retrieve(query=rewritten_query, source_key=source_key, top_k=k)
max_similarity = max((c.similarity for c in chunks), default=0.0)
τ = load_tau(source_key)   # configs/retriever.yaml → tau_langchain_v03 / tau_langchain_v1x

if max_similarity < τ:
    return NO_CONTEXT_RESPONSE   # SSE: meta(noContext=true) → done(NO_CONTEXT)
```

---

### 3.4 단계 4 — Source Adapter

| 항목 | 값 |
| --- | --- |
| **입력** | `list[RetrievedChunk]` |
| **출력** | `list[NormalizedDocument]` |
| **구현체** | `V03SourceAdapter`, `V1xSourceAdapter` |
| **추상화 목적** | v0.3(Docusaurus)·v1.x(Mintlify)의 메타데이터 차이를 `NormalizedDocument` 스키마로 통일 |

```python
class NormalizedDocument(TypedDict):
    chunk_id:     str    # Chroma 내 고유 ID
    source_key:   str    # "langchain_v03" | "langchain_v1x"
    heading_path: str    # "How-To > Memory > ConversationBufferMemory"
    permalink:    str    # GitHub SHA-fixed URL
    text:         str    # 청크 텍스트
    similarity:   float  # 유사도 점수 (0.0~1.0)
```

> 상세 파싱 규칙은 `claude/doc-source.md`를 참조한다.

---

### 3.5 단계 5 — 프롬프트 조립

**시스템 프롬프트 템플릿** (`configs/prompts/qa_system.jinja2`):

```jinja
당신은 LangChain {{ source_key }} 공식 문서 전문 Q&A 어시스턴트입니다.
아래 [참고 문서] 내용만을 근거로 질문에 답하세요.

규칙:
1. [참고 문서]에 없는 내용은 "문서에서 찾을 수 없습니다"라고 명시하세요.
2. {{ source_key }} 이외의 버전 코드·API를 답변에 포함하지 마세요.
3. 코드 예시는 반드시 [참고 문서]의 코드를 기반으로 작성하세요.

[참고 문서]
{% for doc in documents %}
---
출처: {{ doc.heading_path }}
{{ doc.text }}
{% endfor %}
```

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

**컨텍스트 토큰 초과 처리:**
- 조립 전 tiktoken으로 총 토큰 수 계산
- 모델 한도(GPT-4o-mini: 128K) 대비 50% 초과 시 k를 3으로 줄여 재조립
- 재조립 후도 초과 시 대화 이력을 N-1로 줄임
- `ContextTooLongError`는 최후 수단으로만 발생시킴

---

### 3.6 단계 6 — LLM 스트리밍 (SINGLE 모드 전용)

> **SINGLE 모드 전용.** COMPARE 모드는 §5의 Structured Outputs 비스트리밍 흐름을 사용한다.

| 항목 | 값 |
| --- | --- |
| **모델** | `gpt-4o-mini` |
| **temperature** | `0` |
| **stream** | `True` |
| **max_tokens** | `1024` (설정: `configs/models/openai.yaml`) |
| **구현체** | `OpenAIAnswerGenerator.generate_stream()` |

**SSE 이벤트 발행 순서 (SINGLE 모드):**

```python
# 1. meta 이벤트 — LLM 호출 전에 먼저 전송
yield SseEvent(event="meta", data={
    "sources": [asdict(doc) for doc in normalized_docs],
    "source_key": source_key,
})

# 2. token 이벤트 — LLM 스트림에서 수신 즉시 전송
async for chunk in llm_stream:
    text = chunk.choices[0].delta.content or ""
    if text:
        yield SseEvent(event="token", data={"text": text})

# 3. done 이벤트
yield SseEvent(event="done", data={"status": "OK", "finish_reason": "stop"})
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
data: {"status": "NO_CONTEXT"}
```

**구현:**

```python
async def _yield_no_context() -> AsyncIterator[SseEvent]:
    yield SseEvent(event="meta", data={"noContext": True, "sources": []})
    yield SseEvent(event="done", data={"status": "NO_CONTEXT"})
```

> `max_similarity`·`threshold`는 서버 측 로그(`no_context_triggered` 이벤트)에만 기록한다. 클라이언트에 노출하지 않는다.

---

## 5. 비교 모드 — Structured Outputs 처리

COMPARE 모드는 asyncio queue + SSE 인터리빙 방식을 **사용하지 않는다**. OpenAI Structured Outputs로 두 버전의 답변을 단일 비스트리밍 호출로 생성한다.

```python
from pydantic import BaseModel

class CompareResult(BaseModel):
    answerA: str   # source_key_a에 대한 답변
    answerB: str   # source_key_b에 대한 답변


async def compare_pipeline(
    question: str,
    source_key_a: str,
    source_key_b: str,
) -> AsyncIterator[SseEvent]:

    # 1. 두 소스 동시 벡터 검색
    chunks_a, chunks_b = await asyncio.gather(
        retriever.retrieve(query=question, source_key=source_key_a, top_k=5),
        retriever.retrieve(query=question, source_key=source_key_b, top_k=5),
    )

    # 2. meta 이벤트 먼저 전송
    yield SseEvent(event="meta", data={
        "mode": "COMPARE",
        "sources": {
            source_key_a: [asdict(c) for c in chunks_a],
            source_key_b: [asdict(c) for c in chunks_b],
        }
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

    # 4. done 이벤트 1회 반환
    yield SseEvent(event="done", data={
        "status": "OK",
        "compareResult": {
            "answerA": result.answerA,
            "answerB": result.answerB,
        }
    })
```

**에러 처리:** Structured Outputs 파싱 실패(`ValidationError`) 또는 OpenAI 호출 실패 시 `done` 이벤트를 `status: "ERROR"`로 반환한다.

```python
yield SseEvent(event="done", data={"status": "ERROR", "code": "STRUCTURED_OUTPUT_FAILED"})
```

---

## 6. 설정 파일 목록

| 파일 | 주요 설정값 |
| --- | --- |
| `configs/pipeline.yaml` | `history_window` (멀티턴 N턴), `rewrite_model` |
| `configs/retriever.yaml` | `top_k`, `tau_langchain_v03`, `tau_langchain_v1x` |
| `configs/models/openai.yaml` | `model`, `temperature`, `max_tokens` |
| `configs/prompts/qa_system.jinja2` | 단일 모드 시스템 프롬프트 템플릿 |
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
- [ ] **P-4** 멀티턴 재작성 `answer_summary` 생성 방식 — 전체 답변 저장 vs 첫 100자 요약

---

## 변경 이력

| 버전 | 변경 내용 |
| --- | --- |
| v0.1 | 최초 작성 |
| v0.2 | §2.2 비교 모드 Structured Outputs 비스트리밍으로 재작성, §3.3 source_key로 통합(version 제거), §3.4 NormalizedDocument score→similarity/version→source_key, §3.6 seed=42 제거·channel 필드 제거·SINGLE 모드 명시, §4 NO_CONTEXT SSE로 수정, §5 asyncio queue+SSE→Structured Outputs로 전면 재작성, §6 active_collection.json 제거·seed 제거 |
| v0.3 | §2.1 다이어그램 엔드포인트 `/api/chat` → `/api/v1/chat` 수정, §2.2 다이어그램 엔드포인트 `/api/chat (mode="COMPARE")` → `/api/v1/chat/compare` + 파라미터 snake_case 통일(source_key_a·source_key_b), §5 compare_pipeline 파라미터 주석 source_key_a·source_key_b로 정렬 |

---

*end.*
