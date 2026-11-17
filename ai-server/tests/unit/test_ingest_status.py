"""IngestRun 전이 규칙 — 허용 경로와 거부 경로를 모두 확인한다 (정책서 §10.1)."""

import itertools

import pytest

from src.domain.ingest_status import ALLOWED_TRANSITIONS, IngestStatus, can_transition

S = IngestStatus

# 정책서 §10.1 표를 그대로 옮긴 기대값 ("PENDING~VALIDATING → FAILED"는 5개로 펼침)
POLICY_TABLE = {
    (None, S.PENDING),
    (S.PENDING, S.COLLECTING),
    (S.COLLECTING, S.PROCESSING),
    (S.PROCESSING, S.EMBEDDING),
    (S.EMBEDDING, S.VALIDATING),
    (None, S.RESTORING),
    (S.RESTORING, S.VALIDATING),
    (S.VALIDATING, S.READY),
    (S.READY, S.ACTIVE),
    (S.ACTIVE, S.SUPERSEDED),
    (S.SUPERSEDED, S.ACTIVE),
    (S.SUPERSEDED, S.PURGED),
    (S.PENDING, S.FAILED),
    (S.COLLECTING, S.FAILED),
    (S.PROCESSING, S.FAILED),
    (S.EMBEDDING, S.FAILED),
    (S.VALIDATING, S.FAILED),
    (S.FAILED, S.PURGED),
}

ALL_PAIRS = list(itertools.product([None, *S], S))


def test_allowed_set_equals_policy_table() -> None:
    assert ALLOWED_TRANSITIONS == POLICY_TABLE


@pytest.mark.parametrize(("current", "target"), sorted(POLICY_TABLE, key=str))
def test_policy_transitions_are_allowed(current: S | None, target: S) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [pair for pair in ALL_PAIRS if pair not in POLICY_TABLE],
    ids=lambda v: str(v),
)
def test_every_other_transition_is_rejected(current: S | None, target: S) -> None:
    assert not can_transition(current, target)


@pytest.mark.parametrize("terminal", [S.PURGED])
def test_purged_is_terminal(terminal: S) -> None:
    assert not any(can_transition(terminal, target) for target in S)


def test_restoring_failure_is_not_in_policy() -> None:
    # 정책서 표에 RESTORING → FAILED가 없다. 복원 실패 처리는 스냅샷 작업(R-9-1)에서 정한다
    assert not can_transition(S.RESTORING, S.FAILED)
