# 테스트 계획서

> **최종 수정일:** 2026-11-06

---

## 1. 테스트 원칙

| 원칙 | 내용 |
| --- | --- |
| TDD 우선 | DocumentChunker 전처리 규칙·버전 필터 조립·인용 검증·NO_CONTEXT 임계값 판정은 **단위 테스트 선작성**이 필수다 (SDD.md 비기능 요구사항) |
| 설명 가능성 | AI가 생성한 코드도 테스트가 통과해야 한다. PR마다 테스트 커버리지를 포함한다 |
| 격리 | 외부 API(OpenAI) 호출은 `StubEmbeddingClient`·`StubAnswerGenerator`로 격리한다 (interfaces.md 더미 구현체). Spring Boot↔FastAPI 통신은 WireMock으로 대체한다 |
| 재현성 | 확률적 동작이 있는 테스트는 시드를 고정하거나 결정적 경로만 검증한다 |
| 실패 기록 | 실패한 테스트도 PR에서 `skip` 처리하지 않고 해결한 뒤 병합한다 |

---

## 2. 단위 테스트 (8.1-x, TDD 필수 대상)

> 인터페이스 계약 테스트(interfaces.md)와 겹치지 않도록 비즈니스 로직에 집중한다.
> 적용 범위: FastAPI ai-server (Python pytest), Spring Boot backend (JUnit 5)

### 8.1-1: `DocumentChunker` 전처리 규칙 검증

| 항목 | 내용 |
| --- | --- |
| **목적** | 세 전략(A/B/C)이 각각의 계약 불변식을 만족하는지 검증 |
| **관련** | interfaces.md `DocumentChunker`, eval-scenarios.md E2 전략 정의 |

**검증 케이스**

| 케이스 | 조건 | 기대 결과 |
| --- | --- | --- |
| 빈 문서 | `document.content = ""` | `ChunkingError` 발생, 빈 리스트 반환 금지 |
| 단일 청크 미만 | 전체 토큰 수 < `chunk_size` | 청크 1개, 원문과 동일 |
| 코드 블록 보존 (전략 C) | 마크다운 코드 펜스 ```` ``` ```` 포함 문서 | 코드 블록이 단일 청크에 완전히 포함됨 (`span.start`~`span.end` 경계 검증) |
| 오버랩 범위 | 연속 2개 청크 | 오버랩 토큰이 `0 ≤ overlap ≤ chunk_size` 범위 내 |
| 메타데이터 전파 | `ParsedDocument(source_key="langchain_v03")` | 모든 `Chunk.metadata.source_key = "langchain_v03"` |
| 이미 헤더 경계 (전략 C) | `##` 헤더 직전에서 분할 | 헤더가 다음 청크의 첫 줄 |

**불변식 검증** (interfaces.md 7.4에서 발췌)

```python
chunks = chunker.chunk(document)

# 출력이 빈 리스트가 되는 조건은 ChunkingError여야 한다.
# 모든 청크는 메타데이터를 가진다.
assert all(c.metadata is not None for c in chunks)
# 청크 내용이 원문 범위 내에 있음
assert all(document.content[c.span.start:c.span.end] == c.content
           for c in chunks if c.span is not None)
```

### 8.1-2: `Retriever` source_key 필터 조립 검증

| 항목 | 내용 |
| --- | --- |
| **목적** | `source_key`가 Chroma 컬렉션 선택에 올바르게 사용되는지, 미지원 source_key 시 필터링 계약을 지키는지 검증 |
| **관련** | interfaces.md `Retriever`, ADR-004 (버전별 컬렉션 분리), protocol.md E1 |

**검증 케이스**

| 케이스 | 조건 | 기대 결과 |
| --- | --- | --- |
| 올바른 source_key | `retrieve(query, source_key="langchain_v03", top_k=5)` | 반환 청크 전부 `metadata.source_key = "langchain_v03"` |
| 미지원 source_key | `source_key="langchain_v2x"` | `VersionNotFoundError` 발생 |
| 존재하지 않는 컬렉션 | 해당 source_key 컬렉션 미존재 | `VersionNotFoundError` 발생 |
| `top_k=0` | 경계값 | `ValueError` 또는 빈 리스트 (interfaces.md 불변식에 따라) |

**불변식 검증**

```python
chunks = retriever.retrieve(query, source_key, top_k)

# 반환 순서: 유사도 내림차순
assert all(chunks[i].similarity >= chunks[i+1].similarity
           for i in range(len(chunks)-1))
# source_key 오염 없음
assert all(c.metadata.source_key == source_key for c in chunks)
# top_k 초과 없음
assert len(chunks) <= top_k
```

### 8.1-3: NO_CONTEXT 임계값 판정

| 항목 | 내용 |
| --- | --- |
| **목적** | `max_score < τ` 조건에서 LLM 미호출 및 안내 메시지 반환 보장 |
| **관련** | ADR-007 (τ 결정), protocol.md E1, 정책 및 상태.md |

**검증 케이스**

| 케이스 | max_score | τ | 기대 결과 |
| --- | --- | --- | --- |
| 범위 내 질문 | 0.75 | 0.65 | LLM 호출 발생, 청크 반환 |
| 범위 외 질문 | 0.50 | 0.65 | LLM 미호출, `NO_CONTEXT` 응답 |
| 경계값 (동치) | 0.65 | 0.65 | LLM 미호출 (`<` 조건 → 미호출) |
| τ=0.0 | 임의 값 | 0.0 | 항상 LLM 호출 |

**검증 방법**: `StubEmbeddingClient`와 `StubAnswerGenerator`를 사용해 LLM 호출 여부를 `call_count`로 단언.

```python
stub_gen = StubAnswerGenerator()
result = pipeline.answer(query, mock_low_score_chunks, threshold=0.65)

assert result.answer.startswith("[NO_CONTEXT]")
assert stub_gen.call_count == 0  # LLM 호출 없음
```

### 8.1-4: 인용 검증 — `cited_chunks` 메타데이터 정합성

| 항목 | 내용 |
| --- | --- |
| **목적** | 최종 답변에 첨부되는 인용 청크가 실제 검색 결과와 일치하는지 검증 |
| **관련** | interfaces.md `AnswerResult`, DevDocs-RAG API v1.md `meta` SSE 이벤트 |

**검증 케이스**

| 케이스 | 조건 | 기대 결과 |
| --- | --- | --- |
| 정상 인용 | Top-5 청크로 답변 생성 | `AnswerResult.cited_chunks`가 입력 청크 ID와 일치 |
| 중복 인용 없음 | 동일 `chunk_id` 중복 | `cited_chunks`에서 중복 제거 |
| `meta` SSE 이벤트 | 스트리밍 모드 | `meta.sources`의 `heading_path` 형식이 계층 경로 패턴 준수 |

### 8.1-5: Spring Boot JWT 발급·갱신·재사용 거부

| 항목 | 내용 |
| --- | --- |
| **목적** | 발급·만료·재사용 금지 로직이 정책대로 동작하는지 검증 |
| **관련** | 정책 및 상태.md 인증 정책, ADR-xxx (JWT 전략) |

**검증 케이스**

| 케이스 | 조건 | 기대 결과 |
| --- | --- | --- |
| 정상 발급 | 로그인 성공 | Access (30분) + Refresh (7일) 토큰 반환 |
| Access 갱신 | Refresh 토큰으로 `/auth/refresh` 호출 | 새 Access 토큰 발급, 기존 무효화 |
| Refresh 재사용 | 한 번 사용된 Refresh 토큰 재사용 | `TOKEN_REUSE_DETECTED` 401, 해당 계정 세션 전체 무효화 |
| 만료 Access | TTL 경과 후 보호된 API 호출 | `ACCESS_TOKEN_EXPIRED` 401 |
| 위조 서명 | 서명을 임의로 변경한 JWT | `INVALID_TOKEN` 401 |

### 8.1-6: 비로그인 세션 카운터 — 5회 제한

| 항목 | 내용 |
| --- | --- |
| **목적** | 쿠키 기반 세션이 5회 초과 시 올바르게 차단되는지 검증 |
| **관련** | 정책 및 상태.md 비로그인 정책, protocol.md E6 S4 |

**검증 케이스**

| 케이스 | 조건 | 기대 결과 |
| --- | --- | --- |
| 5회 이내 | 1~5회 질문 | 정상 응답 |
| 6번째 요청 | 동일 세션 쿠키로 6번째 | `429 GUEST_QUOTA_EXCEEDED` |
| 세션 없음 | 쿠키 없이 첫 요청 | 세션 쿠키 발급 + 카운터 1 |
| 다른 세션 | 새 쿠키로 첫 요청 | 카운터 초기화, 정상 응답 |

---

## 3. 통합 테스트 (8.2-x)

> Spring Boot ↔ FastAPI ai-server ↔ Chroma가 연결된 상태를 Docker Compose로 검증한다.
> 외부 LLM(OpenAI)은 WireMock으로 대체한다.

### 8.2-1: Spring Boot → FastAPI 타임아웃 처리

| 항목 | 내용 |
| --- | --- |
| **목적** | FastAPI가 10초 이상 응답하지 않을 때 Spring Boot가 올바르게 클라이언트에 에러를 돌려주는지 확인 |
| **관련** | DevDocs-RAG API v1.md 에러 코드, 정책 및 상태.md |

**시나리오**

1. WireMock으로 `/api/v1/chat` FastAPI 엔드포인트를 11초 지연 응답으로 설정
2. Spring Boot `/api/v1/chat` 엔드포인트 호출

**합격 조건**: `504 AI_SERVER_TIMEOUT` 반환. Spring Boot가 타임아웃 전까지 연결을 블록하지 않는다.

### 8.2-2: FastAPI 5xx 시 클라이언트 에러 전달

| 항목 | 내용 |
| --- | --- |
| **목적** | FastAPI가 500 오류를 반환할 때 Spring Boot가 적절한 에러를 클라이언트에 전달하는지 확인 |
| **관련** | DevDocs-RAG API v1.md |

**시나리오**

1. WireMock으로 FastAPI가 `500 Internal Server Error` 반환하도록 설정
2. Spring Boot를 통해 질문 요청

**합격 조건**: `502 AI_SERVER_ERROR` 반환. 내부 오류 메시지(스택 트레이스, FastAPI 경로)가 클라이언트 응답에 포함되지 않는다.

### 8.2-3: 스트림 도중 클라이언트 연결 해제

| 항목 | 내용 |
| --- | --- |
| **목적** | SSE 스트리밍 도중 클라이언트가 연결을 끊을 때 FastAPI가 LLM 호출을 조기 종료하는지 확인 |
| **관련** | DevDocs-RAG API v1.md SSE 스트리밍, ADR-xxx (스트리밍 취소 전략) |

**시나리오**

1. 스트리밍 시작 후 `token` 이벤트 2개 수신 직후 클라이언트 연결 강제 종료
2. WireMock의 OpenAI mock 호출 로그 확인

**합격 조건**: WireMock이 `AbortController`(Python `GeneratorExit`) 처리로 LLM 스트림이 종료된 것을 기록한다. FastAPI 프로세스가 계속 LLM 토큰을 소비하지 않는다.

### 8.2-4: FastAPI ↔ Chroma 연결 — 컬렉션 없음 처리

| 항목 | 내용 |
| --- | --- |
| **목적** | 요청한 source_key 컬렉션이 Chroma에 없을 때 적절한 에러가 반환되는지 확인 |
| **관련** | interfaces.md `VersionNotFoundError`, DevDocs-RAG API v1.md |

**시나리오**: Chroma에 `langchain_v03` 활성 컬렉션 없이 `source_key=langchain_v03` 요청

**합격 조건**: `404 VERSION_NOT_FOUND` 반환.

### 8.2-5: 인덱스 교체 중 조회 무중단

| 항목 | 내용 |
| --- | --- |
| **목적** | 운영 중 인덱스 스냅샷 교체 시 진행 중인 쿼리가 에러 없이 완료되는지 확인 |
| **관련** | ADR-xxx (Chroma 스냅샷 교체 전략), 정책 및 상태.md |

**시나리오**

1. 질문 요청 10개를 비동기로 전송 (각 1초 지연)
2. 2번째 요청 직후 Chroma 컬렉션 교체 스크립트 실행
3. 모든 응답 결과 수집

**합격 조건**: 10개 요청 모두 정상 응답. 교체 전 요청은 이전 컬렉션 결과, 교체 후 요청은 새 컬렉션 결과 반환.

### 8.2-6: SSE 이벤트 순서 및 스키마 검증

| 항목 | 내용 |
| --- | --- |
| **목적** | `meta → token* → done` 순서와 각 이벤트의 JSON 스키마가 명세와 일치하는지 확인 |
| **관련** | DevDocs-RAG API v1.md SSE 명세 |

**합격 조건**

| 조건 | 검증 항목 |
| --- | --- |
| 이벤트 순서 | 첫 이벤트 = `meta`, 마지막 이벤트 = `done`, 중간 이벤트 모두 `token` |
| `meta` 스키마 | `sources[].heading_path`, `sources[].permalink`, `source_key`, `noContext` 필드 존재 |
| `token` 스키마 | `content: string` 필드 존재 |
| `done` 스키마 | `latency_breakdown` 객체 존재 (Embedding·Retrieval·LLM·SSE 단계별 ms 포함) |
| NO_CONTEXT 경로 | `meta(noContext=true, sources=[]) → done(status: "NO_CONTEXT")` 순서로 2개 이벤트 반환 |

### 8.2-7: 비로그인 5회 제한 — E2E 흐름

| 항목 | 내용 |
| --- | --- |
| **목적** | Spring Boot 세션 카운터와 429 차단이 실제 HTTP 흐름에서 동작하는지 확인 |
| **관련** | 정책 및 상태.md, 8.1-6 단위 테스트와 연동 |

**시나리오**: 비로그인 쿠키로 `POST /api/v1/chat` 6회 연속 호출

**합격 조건**: 1~5회 `200 OK`, 6회 `429 GUEST_QUOTA_EXCEEDED`.

### 8.2-8: 로그인·로그아웃 전체 흐름

| 항목 | 내용 |
| --- | --- |
| **목적** | 회원가입 → 로그인 → 질문 → 로그아웃 → 보호된 엔드포인트 접근 차단 흐름 E2E |
| **관련** | DevDocs-RAG API v1.md 인증 API |

**합격 조건**: 로그아웃 후 같은 Access 토큰으로 `POST /api/v1/chat` 호출 시 `401 ACCESS_TOKEN_EXPIRED` 또는 `401 INVALID_TOKEN` 반환.

### 8.2-9: 비교 모드 — 버전 양쪽 동시 질문

| 항목 | 내용 |
| --- | --- |
| **목적** | 비교 모드 `POST /api/v1/chat/compare`가 sourceKeyA·sourceKeyB 각각 독립된 RAG 파이프라인을 호출하고 Structured Outputs로 결과를 반환하는지 확인 |
| **관련** | DevDocs-RAG API v1.md §3.1, 기획서_v1.md 비교 모드 |

**합격 조건**

- 응답에 `answerA`·`answerB` 필드 각각 존재 (OpenAI Structured Outputs `CompareResult` 스키마)
- 각 필드 답변은 해당 sourceKey 컬렉션의 청크에 기반함
- 한쪽 버전이 NO_CONTEXT이더라도 나머지 버전 응답은 정상 반환
- 비교 모드는 Non-streaming (SSE 없음); `meta → done` 이벤트로 완료

### 8.2-10: NO_CONTEXT 경로 E2E

| 항목 | 내용 |
| --- | --- |
| **목적** | 범위 밖 질문(Q-oos 유형)에서 LLM 미호출 및 안내 메시지 반환 흐름 E2E |
| **관련** | protocol.md E1, eval-scenarios.md Q-oos, 8.1-3 단위 테스트와 연동 |

**시나리오**: OOS-001 (Django ORM 관련 질문) 전송, τ를 운영값으로 설정

**합격 조건**

- OpenAI WireMock에 호출 기록 없음
- SSE 이벤트 순서: `meta(noContext=true, sources=[]) → done(status: "NO_CONTEXT")`
- HTTP 상태: `200 OK` (에러가 아님)

### 8.2-11: Chroma 연결 장애 시 ai-server 응답

| 항목 | 내용 |
| --- | --- |
| **목적** | Chroma 프로세스 종료 시 FastAPI가 503을 반환하고 Spring Boot가 이를 클라이언트에 전달하는지 확인 |
| **관련** | 정책 및 상태.md 장애 처리 |

**합격 조건**: Chroma 컨테이너 중지 후 질문 요청 → `503 VECTOR_DB_UNAVAILABLE` 반환.

---

## 4. 성능 테스트 (8.3-x)

> 모든 성능 측정은 EC2 t3.small 배포 환경에서 운영 인덱스(스냅샷 복원 완료) 상태에서 수행한다.

### 8.3-1: Retriever 응답 시간 (p95 ≤ 500ms)

| 항목 | 내용 |
| --- | --- |
| **목적** | Chroma 검색이 SLA를 만족하는지 확인 |
| **관련** | interfaces.md 7.3 성능 제약, protocol.md E5 단계 분해 |

**측정 방법**: Q-ret에서 MEDIUM 난이도 10문항으로 각 50회 호출. `done` 이벤트의 `latency_breakdown.retrieval_ms`로 측정.

**합격 조건**:

| 지표 | 목표 |
| --- | --- |
| 평균 | ≤ 200ms |
| p95 | ≤ 500ms |

### 8.3-2: EmbeddingClient 단일 텍스트 응답 시간 (p95 ≤ 200ms)

| 항목 | 내용 |
| --- | --- |
| **목적** | OpenAI embedding 호출 지연이 TTFT 병목이 되지 않는지 확인 |
| **관련** | interfaces.md 7.3 성능 제약 |

**측정 방법**: 100~500 토큰 텍스트 20개로 각 20회 단독 호출. `latency_breakdown.embedding_ms`로 측정.

**합격 조건**:

| 지표 | 목표 |
| --- | --- |
| p95 | ≤ 200ms |

> 이 목표치는 OpenAI 네트워크 조건에 따라 변동이 크다. 측정값을 보고하고 이상치는 한계로 명시한다.

### 8.3-3: TTFT (첫 토큰 응답 시간)

> protocol.md E5와 동일 절차. 20회 측정, EC2 t3.small.

**합격 조건**:

| 지표 | 목표 |
| --- | --- |
| p50 | ≤ 3초 |
| p95 | ≤ 5초 |

---

## 5. 보안 테스트 (8.4-x)

### 8.4-1: 비인증 접근 차단

**시나리오**: JWT 없이 보호된 모든 엔드포인트 호출.

**합격 조건**: `401 UNAUTHORIZED` 반환. `/health`, `POST /api/v1/auth/login`, `POST /api/v1/auth/register`, `POST /api/v1/auth/refresh` 만 예외.

### 8.4-2: JWT 서명 위조 차단

**시나리오**: 서명 부분(`signature`)을 임의 문자열로 변경한 JWT로 API 호출.

**합격 조건**: `401 INVALID_TOKEN` 반환. 애플리케이션 오류 로그에 스택 트레이스가 클라이언트 응답에 포함되지 않는다.

### 8.4-3: 에러 응답에 내부 정보 미포함

**시나리오**: 존재하지 않는 엔드포인트·잘못된 파라미터·의도적인 500 오류로 여러 에러 유도.

**합격 조건**: 응답 바디에 스택 트레이스, SQL 쿼리, 서버 내부 경로, Chroma 컬렉션명, OpenAI API 키 패턴이 포함되지 않는다.

### 8.4-4: 비밀번호 해시 형식 검증

**시나리오**: 회원가입 후 PostgreSQL에서 `users.password_hash` 직접 확인.

**합격 조건**: bcrypt 형식(`$2b$...`)이다. 평문이나 MD5/SHA 형식이 아니다.

### 8.4-5: 비로그인 연속 요청 — Rate Limit 429 반환

**시나리오**: 비로그인 세션으로 6번째 요청.

**합격 조건**: `429 GUEST_QUOTA_EXCEEDED` 반환. Retry-After 헤더 존재 (또는 로그인 안내 메시지 포함).

---

## 6. 인수 기준 체크리스트 (8.5-x)

SDD.md 각 기능의 인수 기준을 SP1·SP2 발표 전 점검하는 목록이다.

### SP1 중간 발표 인수 기준

| ID | 항목 | 확인 방법 | 상태 |
| --- | --- | --- | --- |
| 8.5-01 | 단일 모드 RAG 질문 응답 E2E 동작 | Postman으로 LangChain v0.3 질문 → SSE 스트림 수신, `meta.sources` 존재 확인 | ⬜ |
| 8.5-02 | NO_CONTEXT 경로 동작 | OOS-001 질문 전송 → `meta(noContext=true) → done(status: NO_CONTEXT)` 수신 | ⬜ |
| 8.5-03 | v0.3·v1.x 컬렉션 분리 인덱스 EC2에 복원 | `validate_index.py` 실행 → 두 컬렉션 청크 수 검증 | ⬜ |
| 8.5-04 | 로그인·질문·히스토리 화면 SP1 배포 | EC2에서 접근 가능, 비로그인 5회 제한 동작 | ⬜ |
| 8.5-05 | E1 혼입률 측정 결과 (E1-N vs E1-C) 보고 | `eval/results/E1/` 결과 파일 존재, 혼입률 표 작성 | ⬜ |
| 8.5-06 | E2 청킹 전략 비교 결과 및 채택 전략 결정 | `eval/results/E2/decision.md` 커밋, Hit@5 비교표 존재 | ⬜ |

### SP2 최종 발표 인수 기준

| ID | 항목 | 확인 방법 | 상태 |
| --- | --- | --- | --- |
| 8.5-10 | 비교 모드 — sourceKeyA·B 동시 응답 | 비교 모드 API 호출 → `answerA`·`answerB` 필드 수신 | ⬜ |
| 8.5-11 | E3 버전 오류율 비교 결과 (L0/L1/R1/R2) | `eval/results/E3/` 버전 오류율 비교표, kappa 보고 | ⬜ |
| 8.5-12 | R2 버전 오류율 ≤ 20% (E3 목표) | `eval/results/E3/decision.md` 에 R2 오류율 명시 | ⬜ |
| 8.5-13 | TTFT p50 ≤ 3s, p95 ≤ 5s (E5) | `eval/results/E5/` 20회 측정 박스플롯 존재 | ⬜ |
| 8.5-14 | k6 부하 테스트 10 VU 오류율 < 1% (E6 S1) | `eval/results/E6/` k6 리포트 HTML 존재 | ⬜ |
| 8.5-15 | 동일 Q-shared 질문으로 R2 재실행 시 동일 버전 오류 판정 | `eval_e3_generate.py --seed 42` 2회 실행, `cited_chunks` ID 목록 동일 | ⬜ |
| 8.5-16 | SP2 데모 리허설 1회 무중단 완주 | 비로그인 → 로그인 → 단일 질문 → 비교 모드 흐름 완주 | ⬜ |

---

## 7. CI/CD 검증 (8.6-x)

| ID | 항목 | 트리거 | 합격 조건 |
| --- | --- | --- | --- |
| 8.6-01 | Python 단위 테스트 전체 통과 | PR → main (ai-server 변경 시) | pytest 8.1-x 전체 pass, 커버리지 ≥ 80% |
| 8.6-02 | Java 단위 테스트 전체 통과 | PR → main (backend 변경 시) | JUnit 8.1-x 전체 pass |
| 8.6-03 | 통합 테스트 통과 | PR → main | Docker Compose 8.2-x 전체 pass |
| 8.6-04 | Docker 빌드 성공 (3개 서비스) | PR → main | ai-server·backend·frontend 빌드 오류 없음 |
| 8.6-05 | Alembic 마이그레이션 무결성 | `migrations/` 변경 시 | `alembic upgrade head` 오류 없음 |
| 8.6-06 | 비밀값 커밋 방지 | PR → main | `.env`·API 키 패턴(`sk-`, `OPENAI_API_KEY`) 감지 시 차단 |
| 8.6-07 | EC2 자동 배포 | main 병합 | 배포 후 `GET /health` → `{"status": "UP"}` |

---

## 8. 테스트 환경

| 환경 | 용도 | 구성 |
| --- | --- | --- |
| 로컬 Docker Compose | 단위·통합 테스트 | `docker-compose.test.yml`. OpenAI API = WireMock, Chroma = 테스트 컬렉션 (소량 샘플 인덱스) |
| EC2 t3.small | 성능·인수 테스트 | 운영 스냅샷 인덱스 복원 완료 상태. E5·E6 측정 시에만 실제 OpenAI 호출 |
| CI (GitHub Actions) | 자동화 | 로컬 Docker Compose 환경과 동일 |

---

## 미결정 사항

| # | 항목 | 기한 |
| --- | --- | --- |
| TP-1 | 8.3-2 EmbeddingClient p95 목표치 — EC2 환경에서 1차 측정 후 조정 가능 | W5 배포 후 |
| TP-2 | 8.1-2 `top_k=0` 처리 방식 — `ValueError` vs 빈 리스트 — interfaces.md 불변식에서 확정 | W2 (interfaces.md 확정 시) |
| TP-3 | 8.2-5 인덱스 교체 중단 없는 전환 전략 — ADR 작성 후 테스트 케이스 세부화 | W4 |
| TP-4 | 8.6-01 Python 커버리지 임계값 (80%) — TDD 대상 모듈 완성 후 현실적으로 조정 가능 | W3 |

---

## 변경 이력

| 버전 | 변경 내용 |
| --- | --- |
| v0.3 | §8.1-5 Access Token TTL 15분 → 30분 수정 |

---

*end.*
