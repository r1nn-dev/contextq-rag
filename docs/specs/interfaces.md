# 컴포넌트 인터페이스 명세

> **최종 수정**: 2026-11-18

---

## 1. 개요

- **목적**: FastAPI AI 서버 내부의 RAG 파이프라인 컴포넌트 간 입출력 계약을 정의한다.
- **범위**: 이 문서는 Python Protocol 기반 인터페이스만 다룬다. FastAPI AI 서버 ↔ Spring Boot 메인 백엔드 간 HTTP 계약은 `docs/specs/api-spec.md`(§6 내부 API, 부록 B SSE)를 참조한다.
- **구현 언어**: Python 3.12

---

## 2. 공통 타입 정의

### 2.1 공유 데이터 타입

```python
from dataclasses import dataclass
from typing import TypedDict, AsyncIterator

@dataclass(frozen=True)
class Section:
    heading_path: str              # 섹션 계층 경로. 예: "Agents > LCEL > Building chains"
    text: str                      # 전처리 완료 본문
    line_numbers: tuple[int, ...]  # text의 각 줄에 대응하는 원문 라인 번호(1부터). len == text 줄 수

    # line_start / line_end = line_numbers[0] / line_numbers[-1]

@dataclass(frozen=True)
class NormalizedDocument:          # Source Adapter 출력 (ADR-006)
    file_path: str                 # 저장소 루트 기준 경로. 예: "src/oss/langchain/agents.mdx"
    title: str                     # 문서 제목 (heading_path 최상위)
    doc_type: str                  # "md" | "mdx" | "ipynb"
    site_url: str                  # 공식 문서 사이트 URL (보조 링크, 불변 보장 없음)
    sections: tuple[Section, ...]  # 문서 순서대로. 본문 50자 미만 섹션은 상위 섹션에 병합된 상태

class Chunk(TypedDict):            # DocumentChunker 출력
    content: str          # 청크 텍스트
    heading_path: str     # 청크가 속한 섹션의 heading_path
    line_start: int       # 원문 내 시작 라인 번호
    line_end: int         # 원문 내 끝 라인 번호 (line_start 이상)

class ChunkMetadata(TypedDict):    # Chroma 저장 메타데이터. 필드 정의는 policy.md §4.2
    chunk_id: str
    source_key: str       # 소스 식별자. 예: "langchain_v03", "langchain_v1x"
    framework: str
    version: str
    ingest_run_id: int
    commit_sha: str       # 40자
    file_path: str
    heading_path: str
    line_start: int
    line_end: int
    permalink: str        # SHA 고정 URL (ADR-007)
    site_url: str
    doc_type: str
    chunk_strategy: str   # "A" | "B" | "C"
    chunk_params_hash: str
    embedding_model: str
    token_count: int
    has_code: bool

class RetrievedChunk(TypedDict):
    chunk_id: str         # 벡터 DB 내 고유 ID
    content: str          # 청크 텍스트
    permalink: str        # 원본 문서 URL (공식 문서 직접 링크)
    source_key: str       # 소스 식별자. 예: "langchain_v03"
    file_path: str        # 소스 저장소 루트 기준 파일 경로 (ChunkMetadata.file_path). 평가 gold 판정에 사용
    heading_path: str     # 섹션 계층 경로. 예: "Agents > LCEL > Building chains"
    token_count: int      # 청크 토큰 수 (ChunkMetadata.token_count). 컨텍스트 예산·평균 컨텍스트 토큰 계산
    site_url: str         # 공식 문서 사이트 URL (ChunkMetadata.site_url). SSE meta.sources[].siteUrl
    similarity: float     # 유사도 점수. 범위: 0.0~1.0. 높을수록 관련성 높음
```

### 2.2 공통 Enum

```python
from enum import Enum

class SourceKey(str, Enum):
    LANGCHAIN_V03 = "langchain_v03"
    LANGCHAIN_V1X = "langchain_v1x"
    # 지원 소스 추가 시 여기에 등록
```

---

## 3. 인터페이스 목록

| 인터페이스명 | 설명 | 초안 | 확정 | 상태 |
| --- | --- | --- | --- | --- |
| `Retriever` | 쿼리로 관련 청크 검색 | r1nn-dev | - | 설계 |
| `AnswerGenerator` | 컨텍스트 기반 단일 모드 답변 스트리밍 생성 | r1nn-dev | - | 설계 |
| `CompareGenerator` | 두 버전 컨텍스트로 비교 결과 구조화 생성 (비교 모드) | r1nn-dev | - | 구현 |
| `QueryRewriter` | 멀티턴 후속 질문을 단독 검색 질의로 재작성 | r1nn-dev | - | 구현 |
| `DocumentChunker` | 문서를 청크로 분할 | r1nn-dev | - | 설계 |
| `EmbeddingClient` | 텍스트를 임베딩 벡터로 변환 | r1nn-dev | - | 설계 |

---

## 4. 인터페이스 상세

### Retriever

| 항목 | 값 |
| --- | --- |
| **목적** | 사용자 쿼리와 source_key 조건으로 관련 문서 청크를 검색한다 |
| **초안** | r1nn-dev |
| **확정** | - |
| **상태** | 설계 |
| **구현체** | `ChromaRetriever` |
| **소비자** | `rag/router.py` (Q&A 엔드포인트) |

#### 메서드 목록

| 메서드명 | 설명 | 동기/비동기 |
| --- | --- | --- |
| `retrieve` | 쿼리로 관련 청크 검색 | sync |

---

#### `retrieve`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `query` | `str` | Y | 사용자 질문 | 비어 있으면 안 됨 |
| `source_key` | `str` | Y | 소스 식별자 | `SourceKey` Enum 값. 예: `"langchain_v03"` |
| `top_k` | `int` | N | 반환할 청크 수 | 1 ≤ top_k ≤ 20. 시그니처 기본값 5(직접 호출용). 서비스는 `configs/rag.yaml` `retrieval.top_k`(8, E2 확정)를 넘긴다 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `list[RetrievedChunk]` | similarity 내림차순 정렬된 청크 목록. 결과 없으면 빈 리스트 반환 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `SourceNotFoundError` | 요청한 source_key가 소스 카탈로그(`ai.sources`)에 없는 경우 (HTTP 404) |
| `SourceUnavailableError` | 해당 source_key가 비활성(`enabled = false`) 소스인 경우 (HTTP 409) |
| `IndexNotActiveError` | 해당 source_key에 ACTIVE run 포인터가 없거나 그 컬렉션이 없는 경우 (HTTP 503) |
| `EmbeddingModelMismatchError` | 컬렉션·청크의 임베딩 모델이 질의 임베딩 모델과 다른 경우 (INV-03, HTTP 500) |
| `EmbeddingError` | 쿼리 임베딩 생성 실패 |

**코드 예시**

```python
from typing import Protocol

class Retriever(Protocol):
    def retrieve(
        self,
        query: str,
        source_key: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """
        사용자 쿼리로 관련 문서 청크를 검색한다.

        Args:
            query: 사용자 질문 텍스트
            source_key: SourceKey Enum 값. 예: "langchain_v03"
            top_k: 반환할 최대 청크 수 (시그니처 기본 5, 서비스는 rag.yaml retrieval.top_k = 8)

        Returns:
            similarity 내림차순 정렬된 RetrievedChunk 목록.
            결과가 없으면 빈 리스트를 반환한다.

        Raises:
            SourceNotFoundError: source_key가 소스 카탈로그에 없는 경우
            SourceUnavailableError: 해당 source_key가 비활성 소스인 경우
            IndexNotActiveError: ACTIVE run 포인터 또는 그 컬렉션이 없는 경우
            EmbeddingModelMismatchError: 인덱스 임베딩 모델이 질의 모델과 다른 경우 (INV-03)
            EmbeddingError: 쿼리 임베딩 생성에 실패한 경우
        """
        ...
```

**구현 노트**
- 반환 목록은 항상 similarity 내림차순 정렬이어야 한다.
- 결과가 없을 때 `None`이 아닌 빈 리스트를 반환한다.
- 1차 격리: `ai.index_pointers`의 ACTIVE run 컬렉션(`{source_key}_run{active_run_id}`) 하나만 조회한다. Chroma `where` 메타데이터 필터는 쓰지 않는다 (ADR-004, `policy.md` §5.3).
- 2차 검증: 결과 청크의 `source_key`·`version`·`ingest_run_id`가 요청 소스의 ACTIVE run과 다르면 폐기하고 ERROR 로그를 남긴다 (INV-02). 폐기된 청크는 반환 목록에서 빠지므로 반환 수가 `top_k`보다 적을 수 있다.
- 요청 시작 시 확정한 ACTIVE run으로 끝까지 조회한다. 포인터는 30초 캐시하며 reload로 즉시 무효화한다 (`policy.md` §2.1).

---

### AnswerGenerator

| 항목 | 값 |
| --- | --- |
| **목적** | 검색된 청크를 컨텍스트로 사용하여 LLM 기반 답변을 생성한다 |
| **초안** | r1nn-dev |
| **확정** | - |
| **상태** | 설계 |
| **구현체** | `OpenAIAnswerGenerator` |
| **소비자** | `rag/router.py` (Q&A 엔드포인트) |

#### 메서드 목록

| 메서드명 | 설명 | 동기/비동기 | 용도 |
| --- | --- | --- | --- |
| `generate_stream` | SSE 스트리밍 답변 생성 | async | SINGLE 모드 |

---

**코드 예시**

```python
from typing import Protocol, AsyncIterator

class AnswerGenerator(Protocol):
    def generate_stream(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        display_name: str,       # 선택 버전 표시명. 예: "LangChain v1.x" (답변 첫 줄 명시, 정책서 §5.5 ③)
        prompt_version: str,     # configs/prompts/ 파일명(확장자 제외). 예: "single_v1"
    ) -> GenerationStream:
        """
        SINGLE 모드 전용 스트리밍 답변 생성.
        라우터가 이 이터레이터를 소비하여 SSE token 이벤트로 감싸 클라이언트에 전송한다.
        chunks의 순서가 인용 번호 [1..n]이다 (meta.sources rank와 같다).

        SSE 이벤트 순서 (라우터 책임):
            meta → token* → done

        Returns:
            GenerationStream — 답변 토큰 텍스트를 순차적으로 yield한다.
            스트림이 끝나면 model·finish_reason·usage가 채워진다.

        Raises:
            PromptNotFoundError: prompt_version 파일이 없음 (호출 즉시)
            LLMCallError: OpenAI 호출 실패, 첫 토큰 10초 초과 (이터레이션 중)
        """
        ...


class TokenUsage(TypedDict):
    prompt: int
    completion: int


class GenerationStream(Protocol):
    """토큰 스트림. 끝까지 소비하거나 aclose()로 닫는다 (클라이언트 취소 시 OpenAI 연결 해제)."""

    model: str | None             # 실제 응답 모델명 (INV-13). 첫 조각을 받은 뒤 채워진다
    finish_reason: str | None     # "stop" | "length" | ... 스트림 종료 후 채워진다
    usage: TokenUsage | None      # 스트림 종료 후 채워진다. 중간에 닫으면 None

    def __aiter__(self) -> AsyncIterator[str]: ...
    async def aclose(self) -> None: ...
```

**구현 노트**
- 프롬프트 템플릿은 `configs/prompts/{prompt_version}.j2`(Jinja2)로 버전 관리한다. 하드코딩 금지.
- `generate_stream` 파라미터: temperature 0, `max_tokens` 1,024, 첫 토큰 10초, 재시도 없음 (`configs/models.yaml` `llm`, 정책서 §5.5·§2.1). 모델은 `LLM_MODEL` 환경 변수가 우선한다.
- sentinel(`[[NO_ANSWER]]`) 감지와 인용 번호 검증은 생성기가 아니라 라우터 조립 단계가 한다 (정책서 §5.4·§5.5).
- COMPARE 모드는 이 인터페이스가 아니라 `CompareGenerator`를 쓴다.

---

### CompareGenerator

| 항목 | 값 |
| --- | --- |
| **목적** | 두 버전의 컨텍스트로 비교 결과(`compareResult`)를 한 번에 생성한다 (ADR-010, 정책서 §5.6) |
| **초안** | r1nn-dev |
| **확정** | - |
| **상태** | 구현 |
| **구현체** | `OpenAICompareGenerator` |
| **소비자** | 비교 모드 파이프라인 (`POST /internal/v1/chat/stream`, `mode=COMPARE`) |

#### 메서드 목록

| 메서드명 | 설명 | 동기/비동기 | 용도 |
| --- | --- | --- | --- |
| `generate_compare` | Structured Outputs 비스트리밍 1회 호출(파싱 실패 시 1회 재시도) | async | COMPARE 모드 |

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `query` | `str` | Y | 사용자 원래 질문 (재작성 질의는 검색에만 쓴다) | 비어 있으면 안 됨 |
| `chunks_a` · `chunks_b` | `Sequence[RetrievedChunk]` | Y | 측별 컨텍스트. 순서가 인용 번호 `A1…`·`B1…` | 근거 없는 측은 빈 시퀀스. 둘 다 비면 호출하지 않는다(INV-07) |
| `display_name_a` · `display_name_b` | `str` | Y | 버전 표시명. 예: "LangChain v0.3" | |
| `prompt_version` | `str` | Y | `configs/prompts/` 파일명(확장자 제외). 예: `compare_v1` | |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `CompareGeneration` | 모델 출력(`CompareResult`, 후처리 전) + `model`·`usage`(재시도 포함 합계)·`attempts` |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `PromptNotFoundError` | `prompt_version` 파일이 없음 (호출 즉시) |
| `CompareParseError` | 파싱 실패(스키마 불일치·`finish_reason=length`·거절·빈 결과)가 재시도 후에도 남음 → `error` `COMPARE_PARSE_ERROR` |
| `LLMCallError` | OpenAI 호출 실패·호출 제한 시간 초과 (재시도 없음) → `error` `LLM_ERROR` |

```python
@dataclass(frozen=True)
class CompareGeneration:
    result: CompareResult          # rag-pipeline.md §5.2 출력 스키마 (후처리 전)
    model: str | None              # 실제 응답 모델명 (INV-13)
    usage: TokenUsage | None       # 재시도 포함 합계
    attempts: int                  # 1 또는 2


class CompareGenerator(Protocol):
    async def generate_compare(
        self,
        query: str,
        chunks_a: Sequence[RetrievedChunk],
        chunks_b: Sequence[RetrievedChunk],
        *,
        display_name_a: str,
        display_name_b: str,
        prompt_version: str,
    ) -> CompareGeneration: ...
```

**구현 노트**
- 파라미터: temperature 0, `max_tokens` 1,500, 호출 제한 시간·파싱 재시도 1회 (`configs/models.yaml` `compare`). 모델은 `LLM_MODEL` 환경 변수가 우선한다.
- 인용 후처리(없는·반대 측 번호 제거, 양쪽 인용 없는 변경점 폐기)와 `no_evidence` 고정은 생성기가 아니라 파이프라인이 한다 (rag-pipeline.md §5.3).

---

### QueryRewriter

| 항목 | 값 |
| --- | --- |
| **목적** | 최근 대화로 후속 질문을 단독 검색 질의로 바꾼다 (ADR-009, 정책서 §5.2) |
| **초안** | r1nn-dev |
| **확정** | - |
| **상태** | 구현 |
| **구현체** | `OpenAIQueryRewriter` (`SkippingRewriter`: 재작성 없이 원래 질문 — 평가·테스트용 기본값) |
| **소비자** | 단일 모드 파이프라인 (`pipeline/single.py`) — 검색 전 단계 |

#### 메서드 목록

| 메서드명 | 설명 | 동기/비동기 | 용도 |
| --- | --- | --- | --- |
| `rewrite` | 이력이 있으면 재작성, 없으면 원래 질문 | async | SINGLE 모드 (비교 모드도 같은 질의 1개로 양쪽 검색, 정책서 §5.6) |

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `question` | `str` | Y | 현재 질문 원문 | trim 후 1~1,000자 |
| `history` | `Sequence[HistoryMessage]` | Y | 최근 대화, 오래된 것부터 (`role`: `user`·`assistant`) | 최대 6개, 메시지당 2,000자. 실패·근거 부족 답변은 보내는 쪽이 뺀다. 빈 시퀀스면 재작성하지 않음 |
| `request_id` | `str` | Y (키워드) | 로그 상관 ID | - |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `RewriteResult` | `query`(검색에 쓸 질의), `rewritten`(재작성 성공 시만 값 → `meta.rewrittenQuery`), `status`(`OK`·`FALLBACK`·`SKIPPED`), `elapsed_ms`(시도했으면 걸린 시간 → `done.latency.rewriteMs`, SKIPPED면 None) |

**예외**

- 없음. 제한 시간(3초) 초과·빈 출력·200자 초과·호출 오류·질문 언어가 바뀐 출력은 원래 질문을 쓰는 `FALLBACK`으로 돌려준다(재작성 실패는 답변 실패가 아니다).

**코드 예시**

```python
class QueryRewriter(Protocol):
    async def rewrite(
        self, question: str, history: Sequence[HistoryMessage], *, request_id: str
    ) -> RewriteResult:
        """
        최근 3턴만 참조하고 이전 assistant 본문은 앞 500자만 쓴다(configs/rag.yaml rewrite).
        재작성 질의는 검색에만 쓰고, 생성 프롬프트에는 원래 질문을 넣는다(ADR-009).
        """
        ...
```

**구현 노트**
- 프롬프트는 `configs/prompts/{rewrite.prompt_version}.j2` 템플릿 하나를 user 메시지로 보낸다. 문구 변경은 새 버전 파일로 한다.
- 호출 파라미터는 `configs/models.yaml` `rewrite`(temperature 0, 비스트리밍, 재시도 없음, 3초).

---

### DocumentChunker

| 항목 | 값 |
| --- | --- |
| **목적** | 파싱된 문서를 검색 가능한 청크 단위로 분할한다 |
| **초안** | r1nn-dev |
| **확정** | - |
| **상태** | 설계 |
| **구현체** | 전략 A(`CharacterTextSplitter` 래핑) · B(`RecursiveCharacterTextSplitter` 래핑) · C(구조 인식, 코드 펜스 원자 단위) — E2 비교 대상 |
| **소비자** | `ingest/pipeline.py` |

#### 메서드 목록

| 메서드명 | 설명 | 동기/비동기 |
| --- | --- | --- |
| `chunk` | 문서를 청크 목록으로 분할 | sync |

---

#### `chunk`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `document` | `NormalizedDocument` | Y | Source Adapter가 전처리한 문서 | `sections`가 비어 있으면 안 됨 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `list[Chunk]` | 분할된 청크 목록. 문서 순서대로, 최소 1개 이상 반환 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `ChunkingError` | 분할 처리 중 오류 발생 |

**코드 예시**

```python
from typing import Protocol

class DocumentChunker(Protocol):
    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        """
        Args:
            document: Source Adapter가 전처리한 문서

        Returns:
            Chunk 목록. 최소 1개.
            각 Chunk의 line_start/line_end는 원문 파일 기준 라인 번호(Section.line_numbers에서 도출).

        Raises:
            ChunkingError: 분할 처리 실패
        """
        ...
```

**구현 노트**
- `line_start`·`line_end`는 원문 파일 기준 라인 번호이어야 한다(라인 앵커 permalink 근거, ADR-007).
- 청크는 섹션 경계를 넘지 않는다. 한 청크의 `heading_path`는 하나다.
- 청크 크기와 오버랩은 `configs/ingest.yaml`에서 읽는다. 하드코딩 금지.
- `chunk_id`·`permalink` 등 `ChunkMetadata` 조립은 청커가 아니라 ingest 파이프라인이 한다(`policy.md` §4.1·§4.2).

---

### EmbeddingClient

| 항목 | 값 |
| --- | --- |
| **목적** | 텍스트 목록을 임베딩 벡터로 일괄 변환한다 |
| **초안** | r1nn-dev |
| **확정** | - |
| **상태** | 설계 |
| **구현체** | `OpenAIEmbeddingClient` |
| **소비자** | `ChromaRetriever`, `ingest/pipeline.py` |

#### 메서드 목록

| 메서드명 | 설명 | 동기/비동기 |
| --- | --- | --- |
| `embed` | 텍스트 목록을 임베딩 벡터 목록으로 변환 | async |

---

#### `embed`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `texts` | `list[str]` | Y | 임베딩할 텍스트 목록 | 빈 리스트 허용 안 됨. 각 항목 비어 있으면 안 됨 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `list[list[float]]` | 입력과 동일한 순서의 임베딩 벡터 목록. `len(결과) == len(texts)` 보장 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `EmbeddingError` | API 호출 실패 또는 반환 벡터 수 불일치 |

**코드 예시**

```python
from typing import Protocol

class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Args:
            texts: 임베딩할 텍스트 목록 (비어 있으면 안 됨)

        Returns:
            입력과 동일한 순서의 임베딩 벡터 목록.
            len(반환값) == len(texts)가 항상 보장된다.

        Raises:
            EmbeddingError: API 호출 실패 또는 순서 불일치
        """
        ...
```

**구현 노트**
- 반환 벡터 수는 반드시 입력 텍스트 수와 동일해야 한다. 불일치 시 `EmbeddingError`를 발생시킨다.
- 대량 처리 시 배치 크기를 `configs/models/`에서 설정 가능하게 한다.

---

## 5. 예외 코드

| 예외 클래스 | 발원 인터페이스 | 발생 조건 | HTTP 코드 | 호출자 대응 |
| --- | --- | --- | --- | --- |
| `SourceNotFoundError` | `Retriever` | 소스 카탈로그에 해당 source_key 없음 | 404 | SOURCE_NOT_FOUND 반환 |
| `SourceUnavailableError` | `Retriever` | 해당 source_key가 비활성 소스 | 409 | SOURCE_UNAVAILABLE 반환 |
| `IndexNotActiveError` | `Retriever` | ACTIVE run 포인터 또는 컬렉션 없음 (INV-01 위반) | 503 | INDEX_NOT_ACTIVE 반환 |
| `EmbeddingModelMismatchError` | `Retriever` | 인덱스 임베딩 모델 ≠ 질의 임베딩 모델 (INV-03) | 500 | EMBEDDING_MODEL_MISMATCH 반환 |
| `EmbeddingError` | `Retriever`, `EmbeddingClient` | 임베딩 API 호출 실패 | 503 | 로그 후 503 반환 |
| `LLMCallError` | `AnswerGenerator`, `CompareGenerator` | LLM API 호출 실패, 첫 토큰 10초 초과(단일)·호출 제한 시간 초과(비교) | 503 | 스트림 시작 후에는 `error` 이벤트 `LLM_ERROR` (INV-09) |
| `CompareParseError` | `CompareGenerator` | 구조화 출력 파싱 실패가 재시도 후에도 남음 | 502 | `error` 이벤트 `COMPARE_PARSE_ERROR` |
| `PromptNotFoundError` | `AnswerGenerator`, `CompareGenerator` | `prompt_version`에 해당하는 프롬프트 파일 없음 | 400 | INVALID_REQUEST 반환 |
| `ContextTooLongError` | `AnswerGenerator` | 컨텍스트 토큰 초과 | 422 | top_k 줄여 재시도 |
| `ChunkingError` | `DocumentChunker` | 청킹 처리 실패 | - | 해당 문서 건너뜀 후 로그 |

```python
class SourceNotFoundError(Exception):
    """요청한 source_key가 소스 카탈로그에 없는 경우 (HTTP 404)"""
    pass

class SourceUnavailableError(Exception):
    """해당 source_key가 비활성 소스인 경우 (HTTP 409)"""
    pass

class IndexNotActiveError(Exception):
    """ACTIVE run 포인터 또는 그 컬렉션이 없는 경우 (HTTP 503)"""
    pass

class EmbeddingModelMismatchError(Exception):
    """인덱스 임베딩 모델이 질의 임베딩 모델과 다른 경우 — INV-03 (HTTP 500)"""
    pass

class EmbeddingError(Exception):
    """임베딩 API 호출 실패 또는 반환값 수 불일치"""
    pass

class LLMCallError(Exception):
    """LLM API 호출 실패 또는 첫 토큰 타임아웃"""
    pass

class CompareParseError(Exception):
    """비교 구조화 출력 파싱 실패 — 재시도 후에도 실패 (COMPARE_PARSE_ERROR)"""
    pass

class PromptNotFoundError(Exception):
    """prompt_version에 해당하는 프롬프트 파일이 없음 (HTTP 400)"""
    pass

class ContextTooLongError(Exception):
    """청크 합산 토큰이 모델 컨텍스트 한도를 초과"""
    pass

class ChunkingError(Exception):
    """문서 청킹 처리 중 오류"""
    pass
```

---

## 6. 제약 및 불변식

### 6.1 입력 제약

- 모든 `str` 파라미터는 빈 문자열(`""`)을 허용하지 않는다.
- `source_key`는 반드시 `SourceKey` Enum에 등록된 값이어야 한다.
- `top_k`는 1 이상 20 이하이어야 한다.

### 6.2 출력 제약

- `Retriever.retrieve()`는 `None`을 반환하지 않는다. 결과 없으면 빈 리스트를 반환한다.
- `EmbeddingClient.embed()`의 반환 벡터 수는 항상 입력 텍스트 수와 같다.
- 비교 모드 `done.compareResult`의 인용 번호는 후처리 뒤 항상 그 측 출처 범위 안에 있다 (`CompareGenerator` 출력은 후처리 전, rag-pipeline.md §5.3).

### 6.3 성능 제약

- `Retriever.retrieve()` p95: 500ms 이내 (임베딩 생성 포함)
- `CompareGenerator.generate_compare()`: 비교 모드 전체 p50 ≤ 12초, 상한 30초 (정책서 §11·§2.1)
- `EmbeddingClient.embed()` 단일 텍스트 p95: 200ms 이내

### 6.4 불변식

```
[항상 참] Retriever.retrieve()의 반환 목록은 similarity 내림차순 정렬이다.
[항상 참] RetrievedChunk.similarity는 0.0 ≤ similarity ≤ 1.0이다.
[항상 참] len(EmbeddingClient.embed(texts)) == len(texts)이다.
[항상 참] Chunk.line_end >= Chunk.line_start이다.
```

---

## 변경 이력

| 버전 | 변경 내용 |
| --- | --- |
| v0.1 | 최초 작성 |
| v0.2 | ChunkMetadata 필드 수정(source_url→permalink, section_title→heading_path, char→line 오프셋), Framework Enum → SourceKey Enum(REACT/NEXTJS 제거), Retriever.retrieve() source_key 단일 파라미터로 통합, 예외 타입 SourceNotFoundError/SourceUnavailableError로 교체, generate_stream() SINGLE 모드 SSE 계약 명시 |
| v0.3 | `ParsedDocument` 제거, Source Adapter 출력 `NormalizedDocument`·`Section` 정의, `DocumentChunker` 입력을 `NormalizedDocument`로 변경, `Chunk`·`ChunkMetadata`를 policy.md §4.2 필수 필드 기준으로 분리, 청킹 설정 위치 `configs/ingest.yaml` |
| v0.4 | `RetrievedChunk`에 `file_path`·`token_count` 추가 (평가 러너의 gold 판정·평균 컨텍스트 토큰, 정책서 §5.3 컨텍스트 예산). 기존 필드 변경 없음 |
| v0.5 | `RetrievedChunk`에 `site_url` 추가 (SSE meta 출처 카드). `Retriever` 예외에 `IndexNotActiveError`·`EmbeddingModelMismatchError` 추가, `SourceNotFoundError`·`SourceUnavailableError` 조건 구체화. 구현 노트: `where` 필터 → ACTIVE 컬렉션 지정 + 2차 메타데이터 검증 (ADR-004) |
| v0.6 | `AnswerGenerator.generate_stream`: 키워드 입력 `display_name`·`prompt_version` 추가, 반환을 `GenerationStream`(토큰 + 종료 후 `model`·`finish_reason`·`usage`)으로 구체화, `PromptNotFoundError` 추가 |
| v0.7 | 비교 모드 생성을 `AnswerGenerator.generate`(미구현)에서 `CompareGenerator.generate_compare`로 분리 — 두 측 청크·표시명 입력, `CompareGeneration` 반환, `CompareParseError` 추가 (R-8-1) |
| v0.8 | §2.1 쓰는 곳이 없는 `AnswerResult` 삭제 — 단일 모드 결과는 `GenerationStream`, 비교 모드는 `CompareGeneration` (R-8-5) |

---
*end.*
