# 컴포넌트 인터페이스 명세

> **최종 수정**: 2026-11-05

---

## 1. 개요

- **목적**: FastAPI AI 서버 내부의 RAG 파이프라인 컴포넌트 간 입출력 계약을 정의한다.
- **범위**: 이 문서는 Python Protocol 기반 인터페이스만 다룬다. FastAPI AI 서버 ↔ Spring Boot 메인 백엔드 간 HTTP 계약은 `DevDocs-RAG API v1.md`를 참조한다.
- **구현 언어**: Python 3.12

---

## 2. 공통 타입 정의

### 2.1 공유 데이터 타입

```python
from typing import TypedDict, AsyncIterator

class ChunkMetadata(TypedDict):
    permalink: str        # 원본 문서 URL (공식 문서 직접 링크)
    source_key: str       # 소스 식별자. 예: "langchain_v03", "langchain_v1x"
    heading_path: str     # 섹션 계층 경로. 예: "Agents > LCEL > Building chains"
    line_start: int       # 원문 내 시작 라인 번호
    line_end: int         # 원문 내 끝 라인 번호

class Chunk(TypedDict):
    content: str          # 청크 텍스트
    metadata: ChunkMetadata

class RetrievedChunk(TypedDict):
    chunk_id: str         # 벡터 DB 내 고유 ID
    content: str          # 청크 텍스트
    permalink: str        # 원본 문서 URL (공식 문서 직접 링크)
    source_key: str       # 소스 식별자. 예: "langchain_v03"
    heading_path: str     # 섹션 계층 경로. 예: "Agents > LCEL > Building chains"
    similarity: float     # 유사도 점수. 범위: 0.0~1.0. 높을수록 관련성 높음

class ParsedDocument(TypedDict):
    url: str              # 원본 문서 URL
    source_key: str       # 소스 식별자. 예: "langchain_v03"
    title: str            # 문서 제목
    content: str          # 파싱된 본문 (마크다운)

class AnswerResult(TypedDict):
    answer: str                          # 생성된 답변 텍스트
    source_chunks: list[RetrievedChunk]  # 답변 근거 청크 목록
    model: str                           # 사용된 LLM 모델명
    prompt_tokens: int                   # 프롬프트 토큰 수
    completion_tokens: int               # 답변 토큰 수
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
| `AnswerGenerator` | 컨텍스트 기반 답변 생성 | r1nn-dev | - | 설계 |
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
| `top_k` | `int` | N | 반환할 청크 수 | 1 ≤ top_k ≤ 20. 기본값 5 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `list[RetrievedChunk]` | similarity 내림차순 정렬된 청크 목록. 결과 없으면 빈 리스트 반환 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `SourceNotFoundError` | 요청한 source_key가 벡터 DB에 존재하지 않는 경우 (HTTP 404) |
| `SourceUnavailableError` | 해당 source_key 인덱스가 비활성 상태인 경우 (HTTP 409) |
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
            top_k: 반환할 최대 청크 수 (기본 5)

        Returns:
            similarity 내림차순 정렬된 RetrievedChunk 목록.
            결과가 없으면 빈 리스트를 반환한다.

        Raises:
            SourceNotFoundError: source_key가 벡터 DB에 없는 경우
            SourceUnavailableError: 해당 source_key 인덱스가 비활성 상태인 경우
            EmbeddingError: 쿼리 임베딩 생성에 실패한 경우
        """
        ...
```

**구현 노트**
- 반환 목록은 항상 similarity 내림차순 정렬이어야 한다.
- 결과가 없을 때 `None`이 아닌 빈 리스트를 반환한다.
- source_key 필터는 Chroma `where` 절 메타데이터 필터로 구현한다.

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
| `generate` | 단일 답변 생성 (비스트리밍) | async | COMPARE 모드 (Structured Outputs) |
| `generate_stream` | SSE 스트리밍 답변 생성 | async | SINGLE 모드 |

---

#### `generate`

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 | 제약 |
| --- | --- | --- | --- | --- |
| `query` | `str` | Y | 사용자 질문 | 비어 있으면 안 됨 |
| `chunks` | `list[RetrievedChunk]` | Y | 검색된 컨텍스트 청크 | 빈 리스트 허용 — 안내 메시지 반환 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `AnswerResult` | 생성된 답변 및 메타데이터 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `LLMCallError` | OpenAI API 호출 실패 (rate limit, timeout 등) |
| `ContextTooLongError` | 청크 합산 토큰이 모델 컨텍스트 한도를 초과한 경우 |

**코드 예시**

```python
from typing import Protocol, AsyncIterator

class AnswerGenerator(Protocol):
    async def generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> AnswerResult:
        """
        검색된 청크를 컨텍스트로 LLM 답변을 생성한다.
        COMPARE 모드: OpenAI Structured Outputs로 비스트리밍 호출 후 한 번에 반환.

        Args:
            query: 사용자 질문
            chunks: Retriever가 반환한 청크 목록.
                    빈 리스트이면 "검색된 문서 없음" 안내 메시지를 반환한다.

        Returns:
            AnswerResult — 답변, 출처 청크, 토큰 사용량 포함

        Raises:
            LLMCallError: OpenAI API 호출 실패
            ContextTooLongError: 컨텍스트 토큰 초과
        """
        ...

    async def generate_stream(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> AsyncIterator[str]:
        """
        SINGLE 모드 전용 스트리밍 답변 생성.
        라우터가 이 이터레이터를 소비하여 SSE token 이벤트로 감싸 클라이언트에 전송한다.
        완료 시 StopAsyncIteration을 자연스럽게 발생시킨다.

        SSE 이벤트 순서 (라우터 책임):
            meta → token* → done

        Returns:
            답변 토큰 텍스트를 순차적으로 yield한다.
        """
        ...
```

**구현 노트**
- `chunks`가 빈 리스트이면 `"검색된 문서가 없어 답변할 수 없습니다."` 형태의 안내를 담은 `AnswerResult`를 반환한다. 예외를 발생시키지 않는다.
- 프롬프트 템플릿은 `configs/prompts/`에서 버전 관리한다. 하드코딩 금지.
- COMPARE 모드는 `generate()`를 사용하며, OpenAI Structured Outputs JSON 스키마를 적용해 비스트리밍으로 호출한다. token 이벤트 없이 `done` 이벤트 1회만 발생한다.

---

### DocumentChunker

| 항목 | 값 |
| --- | --- |
| **목적** | 파싱된 문서를 검색 가능한 청크 단위로 분할한다 |
| **초안** | r1nn-dev |
| **확정** | - |
| **상태** | 설계 |
| **구현체** | `FixedSizeChunker`, `RecursiveChunker` (실험 과제 A) |
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
| `document` | `ParsedDocument` | Y | 파싱된 원본 문서 | `content`가 비어 있으면 안 됨 |

**반환값**

| 타입 | 설명 |
| --- | --- |
| `list[Chunk]` | 분할된 청크 목록. 최소 1개 이상 반환 |

**예외**

| 예외 클래스 | 발생 조건 |
| --- | --- |
| `ChunkingError` | 분할 처리 중 오류 발생 |

**코드 예시**

```python
from typing import Protocol

class DocumentChunker(Protocol):
    def chunk(self, document: ParsedDocument) -> list[Chunk]:
        """
        Args:
            document: 파싱된 문서

        Returns:
            Chunk 목록. 최소 1개.
            각 Chunk의 metadata.line_start/line_end는 document.content 기준 라인 번호.

        Raises:
            ChunkingError: 분할 처리 실패
        """
        ...
```

**구현 노트**
- `line_start`·`line_end`는 `document.content` 기준 라인 번호이어야 한다.
- 청크 크기와 오버랩은 `configs/retrieval/`에서 읽는다. 하드코딩 금지.

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
| `SourceNotFoundError` | `Retriever` | 벡터 DB에 해당 source_key 없음 | 404 | SOURCE_NOT_FOUND 반환 |
| `SourceUnavailableError` | `Retriever` | 해당 source_key 인덱스가 비활성 상태 | 409 | SOURCE_UNAVAILABLE 반환 |
| `EmbeddingError` | `Retriever`, `EmbeddingClient` | 임베딩 API 호출 실패 | 503 | 로그 후 503 반환 |
| `LLMCallError` | `AnswerGenerator` | LLM API 호출 실패 | 503 | 로그 후 503 반환 |
| `ContextTooLongError` | `AnswerGenerator` | 컨텍스트 토큰 초과 | 422 | top_k 줄여 재시도 |
| `ChunkingError` | `DocumentChunker` | 청킹 처리 실패 | - | 해당 문서 건너뜀 후 로그 |

```python
class SourceNotFoundError(Exception):
    """요청한 source_key가 벡터 DB에 존재하지 않는 경우 (HTTP 404)"""
    pass

class SourceUnavailableError(Exception):
    """해당 source_key 인덱스가 비활성 상태인 경우 (HTTP 409)"""
    pass

class EmbeddingError(Exception):
    """임베딩 API 호출 실패 또는 반환값 수 불일치"""
    pass

class LLMCallError(Exception):
    """LLM API 호출 실패"""
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
- `AnswerGenerator.generate()`는 `chunks`가 빈 리스트여도 예외를 발생시키지 않는다.

### 6.3 성능 제약

- `Retriever.retrieve()` p95: 500ms 이내 (임베딩 생성 포함)
- `AnswerGenerator.generate()` p95: 10,000ms 이내 (LLM 응답 포함)
- `EmbeddingClient.embed()` 단일 텍스트 p95: 200ms 이내

### 6.4 불변식

```
[항상 참] Retriever.retrieve()의 반환 목록은 similarity 내림차순 정렬이다.
[항상 참] RetrievedChunk.similarity는 0.0 ≤ similarity ≤ 1.0이다.
[항상 참] len(EmbeddingClient.embed(texts)) == len(texts)이다.
[항상 참] Chunk.metadata.line_end > Chunk.metadata.line_start이다.
[항상 참] AnswerResult.source_chunks는 generate()에 전달된 chunks의 부분집합이다.
```

---

## 변경 이력

| 버전 | 변경 내용 |
| --- | --- |
| v0.1 | 최초 작성 |
| v0.2 | ChunkMetadata 필드 수정(source_url→permalink, section_title→heading_path, char→line 오프셋), Framework Enum → SourceKey Enum(REACT/NEXTJS 제거), Retriever.retrieve() source_key 단일 파라미터로 통합, 예외 타입 SourceNotFoundError/SourceUnavailableError로 교체, generate_stream() SINGLE 모드 SSE 계약 명시 |

---
*end.*
