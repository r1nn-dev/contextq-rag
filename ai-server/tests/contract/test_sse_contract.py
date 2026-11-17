import copy
from typing import Any

import pytest

from tests.contract.sse_contract import (
    ContractViolation,
    Leg,
    example_names,
    load_example,
    validate_event,
    validate_stream,
)

LEGS: list[Leg] = ["client", "upstream"]


@pytest.mark.parametrize(
    ("leg", "name"), [(leg, name) for leg in LEGS for name in example_names(leg)]
)
def test_contract_examples_are_valid(leg: Leg, name: str) -> None:
    validate_stream(load_example(leg, name), leg)


def test_both_legs_have_examples() -> None:
    assert example_names("client")
    assert example_names("upstream")


def _single(leg: Leg = "upstream") -> list[dict[str, Any]]:
    return copy.deepcopy(load_example(leg, "single-completed"))


# --- 스키마 위반 -------------------------------------------------------------


def test_snake_case_field_is_rejected() -> None:
    event = {
        "event": "error",
        "code": "LLM_ERROR",
        "message": "m",
        "request_id": "r",
        "partial": False,
    }
    with pytest.raises(ContractViolation, match="스키마 위반"):
        validate_event(event, "upstream")


def test_client_meta_requires_conversation_and_message_ids() -> None:
    meta = _single("upstream")[0]
    with pytest.raises(ContractViolation):
        validate_event(meta, "client")


def test_upstream_meta_rejects_conversation_id() -> None:
    meta = _single("client")[0]
    with pytest.raises(ContractViolation):
        validate_event(meta, "upstream")


def test_unknown_done_status_is_rejected() -> None:
    events = _single()
    events[-1]["status"] = "OK"
    with pytest.raises(ContractViolation):
        validate_stream(events, "upstream")


def test_no_context_meta_must_not_carry_sources() -> None:
    meta = _single()[0]
    meta["noContext"] = True
    with pytest.raises(ContractViolation):
        validate_event(meta, "upstream")


def test_compare_fields_come_in_pairs() -> None:
    meta = copy.deepcopy(load_example("upstream", "compare-completed")[0])
    del meta["sourceKeyB"]
    with pytest.raises(ContractViolation):
        validate_event(meta, "upstream")


# --- 순서 위반 (INV-06) --------------------------------------------------------


def test_empty_stream_is_rejected() -> None:
    with pytest.raises(ContractViolation, match="빈 스트림"):
        validate_stream([], "upstream")


def test_token_before_meta_is_rejected() -> None:
    events = _single()
    events.insert(0, events.pop(1))
    with pytest.raises(ContractViolation, match="첫 이벤트"):
        validate_stream(events, "upstream")


def test_duplicate_meta_is_rejected() -> None:
    events = _single()
    events.insert(1, copy.deepcopy(events[0]))
    with pytest.raises(ContractViolation, match="meta는 정확히 1회"):
        validate_stream(events, "upstream")


def test_missing_terminal_is_rejected() -> None:
    events = _single()[:-1]
    with pytest.raises(ContractViolation, match="마지막 이벤트"):
        validate_stream(events, "upstream")


def test_event_after_terminal_is_rejected() -> None:
    events = _single()
    events.append({"event": "token", "t": "late"})
    with pytest.raises(ContractViolation):
        validate_stream(events, "upstream")


def test_double_terminal_is_rejected() -> None:
    events = _single()
    events.append(
        {"event": "error", "code": "LLM_ERROR", "message": "m", "requestId": "r", "partial": True}
    )
    with pytest.raises(ContractViolation, match="종결 이벤트"):
        validate_stream(events, "upstream")


def test_pre_meta_error_must_not_be_partial() -> None:
    events = copy.deepcopy(load_example("upstream", "error-before-meta"))
    events[0]["partial"] = True
    with pytest.raises(ContractViolation, match="partial=false"):
        validate_stream(events, "upstream")


def test_error_partial_must_match_token_presence() -> None:
    events = copy.deepcopy(load_example("upstream", "error-midstream"))
    events[-1]["partial"] = False
    with pytest.raises(ContractViolation, match="partial"):
        validate_stream(events, "upstream")


def test_compare_stream_has_no_tokens() -> None:
    events = copy.deepcopy(load_example("upstream", "compare-completed"))
    events.insert(1, {"event": "token", "t": "x"})
    with pytest.raises(ContractViolation, match="비교 모드"):
        validate_stream(events, "upstream")


def test_no_context_stream_ends_with_no_context_status() -> None:
    events = copy.deepcopy(load_example("upstream", "single-no-context"))
    events[-1]["status"] = "COMPLETED"
    with pytest.raises(ContractViolation, match="NO_CONTEXT"):
        validate_stream(events, "upstream")
