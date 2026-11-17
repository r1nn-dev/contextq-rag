"""수집 실행(IngestRun) 상태와 전이 규칙 — 정책서 §10.1.

표에 없는 전이는 모두 거부한다. `None`은 "run이 아직 없음"(생성 전이)을 뜻한다.
"""

from enum import StrEnum


class IngestStatus(StrEnum):
    PENDING = "PENDING"
    COLLECTING = "COLLECTING"
    PROCESSING = "PROCESSING"
    EMBEDDING = "EMBEDDING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    PURGED = "PURGED"
    RESTORING = "RESTORING"
    FAILED = "FAILED"


S = IngestStatus

# 실패 전이가 허용되는 진행 단계 (정책서 §10.1 "PENDING~VALIDATING → FAILED")
FAILABLE: frozenset[IngestStatus] = frozenset(
    {S.PENDING, S.COLLECTING, S.PROCESSING, S.EMBEDDING, S.VALIDATING}
)

ALLOWED_TRANSITIONS: frozenset[tuple[IngestStatus | None, IngestStatus]] = frozenset(
    {
        (None, S.PENDING),  # make ingest
        (S.PENDING, S.COLLECTING),
        (S.COLLECTING, S.PROCESSING),
        (S.PROCESSING, S.EMBEDDING),
        (S.EMBEDDING, S.VALIDATING),
        (None, S.RESTORING),  # make restore-index
        (S.RESTORING, S.VALIDATING),
        (S.VALIDATING, S.READY),
        (S.READY, S.ACTIVE),  # make activate-index
        (S.ACTIVE, S.SUPERSEDED),
        (S.SUPERSEDED, S.ACTIVE),  # make rollback-index
        (S.SUPERSEDED, S.PURGED),
        *((stage, S.FAILED) for stage in FAILABLE),
        (S.FAILED, S.PURGED),
    }
)


def can_transition(current: IngestStatus | None, target: IngestStatus) -> bool:
    """정책서 §10.1 표에 있는 전이인지 판정한다."""
    return (current, target) in ALLOWED_TRANSITIONS
