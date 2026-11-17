"""검색 예외 — interfaces.md §5, 정책서 §9.2 오류 코드.

각 예외는 내부 API가 그대로 쓸 오류 코드와 HTTP 상태를 갖는다.
질의 임베딩 실패는 `src.ingest.embedder.EmbeddingError`를 그대로 쓴다 (interfaces.md §5).
"""


class RetrievalError(Exception):
    code: str = "INTERNAL_ERROR"
    http_status: int = 500


class SourceNotFoundError(RetrievalError):
    """소스 카탈로그(`ai.sources`)에 없는 source_key."""

    code = "SOURCE_NOT_FOUND"
    http_status = 404


class SourceUnavailableError(RetrievalError):
    """비활성(`enabled = false`) 소스."""

    code = "SOURCE_UNAVAILABLE"
    http_status = 409


class IndexNotActiveError(RetrievalError):
    """ACTIVE run 포인터 또는 그 컬렉션이 없음 (INV-01 위반, 장애)."""

    code = "INDEX_NOT_ACTIVE"
    http_status = 503


class EmbeddingModelMismatchError(RetrievalError):
    """인덱스 임베딩 모델이 질의 임베딩 모델과 다름 (INV-03)."""

    code = "EMBEDDING_MODEL_MISMATCH"
    http_status = 500
