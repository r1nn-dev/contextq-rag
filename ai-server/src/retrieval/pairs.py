"""비교 쌍 확인 — 정책서 §3.2 "`ai.compare_pairs`에 정의된 쌍만 허용, A = 구버전, B = 신버전".

`compare_pairs`는 [IMMUTABLE] 테이블(db-design §3.10)이라 처음 읽은 값을 프로세스 동안 쓴다.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.tables import ComparePair


class PairSource(Protocol):
    def allows(self, source_key_a: str, source_key_b: str) -> bool: ...


class ComparePairCatalog:
    """DB의 비교 쌍. 순서까지 같아야 허용한다((v1.x, v0.3)은 거부)."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._pairs: frozenset[tuple[str, str]] | None = None
        self._lock = threading.Lock()

    def allows(self, source_key_a: str, source_key_b: str) -> bool:
        return (source_key_a, source_key_b) in self._load()

    def _load(self) -> frozenset[tuple[str, str]]:
        with self._lock:
            if self._pairs is None:
                with self._session_factory() as session:
                    query = select(ComparePair.source_key_a, ComparePair.source_key_b)
                    self._pairs = frozenset((a, b) for a, b in session.execute(query))
            return self._pairs


@dataclass(frozen=True)
class StaticPairs:
    """고정 비교 쌍 — 테스트·평가 러너용."""

    pairs: frozenset[tuple[str, str]]

    def allows(self, source_key_a: str, source_key_b: str) -> bool:
        return (source_key_a, source_key_b) in self.pairs
