"""활성 인덱스 포인터 조회와 캐시 — ADR-004, 정책서 §2.1·§4.5, db-design §3.12.

- 소스의 ACTIVE run은 `ai.index_pointers` 1행이 가리킨다. 컬렉션 이름은 이 run id로만 만든다.
- 조회 결과(`ActiveIndex`)는 30초 캐시한다. reload API가 즉시 무효화한다 (정책서 §4.5).
- 실패(소스 없음·비활성·포인터 없음)는 캐시하지 않는다 → 활성화 직후 바로 반영된다.
- 요청은 시작할 때 `ActiveIndex`를 한 번 확정하고 끝까지 그 run으로 검색한다.
"""

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.ingest_status import IngestStatus
from src.domain.tables import IndexPointer, IngestRun, Source
from src.ingest.store import collection_name
from src.retrieval.errors import IndexNotActiveError, SourceNotFoundError, SourceUnavailableError

POINTER_CACHE_TTL_SECONDS = 30.0  # 정책서 §2.1 "ai-server 활성 인덱스 포인터 캐시"


@dataclass(frozen=True)
class ActiveIndex:
    """요청이 검색할 run 스냅샷 — SSE meta(ingestRunId·commitSha·ingestedAt)의 원천 (INV-13)."""

    source_key: str
    version: str  # ai.sources.version_label — 청크 메타데이터 `version`과 같다
    run_id: int
    commit_sha: str | None
    ingested_at: date | None
    chunk_count: int | None
    embedding_model: str | None
    display_name: str = ""  # ai.sources.display_name — 답변 첫 줄 버전 표시 (정책서 §5.5 ③)

    @property
    def collection(self) -> str:
        return collection_name(self.source_key, self.run_id)


class PointerSource(Protocol):
    def get(self, source_key: str) -> ActiveIndex: ...


def load_active_index(session: Session, source_key: str) -> ActiveIndex:
    """소스 카탈로그 → 포인터 → run 순서로 확인해 ACTIVE run 스냅샷을 만든다."""
    source = session.scalar(select(Source).where(Source.source_key == source_key))
    if source is None:
        raise SourceNotFoundError(f"등록되지 않은 소스입니다: {source_key}")
    if not source.enabled:
        raise SourceUnavailableError(f"비활성 소스입니다: {source_key}")
    pointer = session.get(IndexPointer, source_key)
    if pointer is None:
        raise IndexNotActiveError(f"{source_key}에 ACTIVE run이 없습니다")
    run = session.get(IngestRun, pointer.active_run_id)
    if run is None or run.status != IngestStatus.ACTIVE:
        status = run.status if run is not None else "없음"
        raise IndexNotActiveError(
            f"{source_key} 포인터가 ACTIVE가 아닌 run을 가리킵니다: "
            f"run {pointer.active_run_id}({status})"
        )
    finished = run.completed_at or run.started_at
    return ActiveIndex(
        source_key=source_key,
        version=source.version_label,
        run_id=run.id,
        commit_sha=run.commit_sha,
        ingested_at=finished.date() if finished else None,
        chunk_count=run.chunk_count,
        embedding_model=run.embedding_model,
        display_name=source.display_name,
    )


class PointerCache:
    """소스별 `ActiveIndex` TTL 캐시. 서버 스레드(검색)와 이벤트 루프(reload)가 함께 쓴다."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        ttl_seconds: float = POINTER_CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: dict[str, tuple[float, ActiveIndex]] = {}
        self._lock = threading.Lock()

    def get(self, source_key: str) -> ActiveIndex:
        now = self._clock()
        with self._lock:
            cached = self._entries.get(source_key)
        if cached is not None and now < cached[0]:
            return cached[1]
        with self._session_factory() as session:
            index = load_active_index(session, source_key)
        with self._lock:
            self._entries[source_key] = (now + self._ttl, index)
        return index

    def invalidate(self, source_key: str | None = None) -> None:
        """reload — 소스 하나 또는 전체 캐시를 지운다. 다음 `get`이 DB를 다시 읽는다."""
        with self._lock:
            if source_key is None:
                self._entries.clear()
            else:
                self._entries.pop(source_key, None)


@dataclass(frozen=True)
class StaticPointers:
    """미리 확정한 `ActiveIndex` 묶음 — 평가 러너가 실행 동안 run을 고정할 때 쓴다."""

    indexes: Mapping[str, ActiveIndex]

    def get(self, source_key: str) -> ActiveIndex:
        try:
            return self.indexes[source_key]
        except KeyError:
            raise IndexNotActiveError(f"{source_key}에 확정된 ACTIVE run이 없습니다") from None
