"""SSE 이벤트 계약 검증기.

- 이벤트 형식: `contracts/sse-events.schema.json` (API 명세 부록 B)
- 이벤트 순서: meta → token* → (done | error), meta와 종결 이벤트는 각각 1회 (정책서 INV-06)
  meta 전 오류는 error 단독·partial=false (API 명세 부록 B.1 오류 경로)

R-4-4(ai-server SSE 생산) 테스트가 `validate_stream(events, leg="upstream")`으로 재사용한다.
"""

import copy
import json
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator

Leg = Literal["client", "upstream"]
Event = Mapping[str, Any]

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"
SCHEMA_PATH = CONTRACTS_DIR / "sse-events.schema.json"

# 구간별 진입점 — 루트는 client 구간, upstream 구간은 $defs/upstreamEvent
_ENTRY_POINTS: dict[Leg, str] = {
    "client": "#/$defs/clientEvent",
    "upstream": "#/$defs/upstreamEvent",
}
_TERMINAL = {"done", "error"}


class ContractViolation(AssertionError):
    """스키마 또는 순서 규칙 위반."""


@cache
def _validator(leg: Leg) -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    entry = copy.deepcopy(schema)
    entry["$ref"] = _ENTRY_POINTS[leg]
    Draft202012Validator.check_schema(entry)
    return Draft202012Validator(entry)


def validate_event(event: Event, leg: Leg = "client") -> None:
    """이벤트 1개를 스키마로 검증한다."""
    errors = sorted(_validator(leg).iter_errors(event), key=lambda e: list(e.path))
    if errors:
        details = "; ".join(f"{list(e.path)}: {e.message}" for e in errors)
        raise ContractViolation(f"{event.get('event')!r} 이벤트 스키마 위반: {details}")


def validate_stream(events: Sequence[Event], leg: Leg = "client") -> None:
    """스트림 전체를 스키마와 순서 규칙으로 검증한다."""
    if not events:
        raise ContractViolation("빈 스트림: 종결 이벤트가 없습니다")

    for event in events:
        validate_event(event, leg)

    kinds = [event["event"] for event in events]

    # meta 전 오류: error 단독, partial=false
    if kinds[0] == "error":
        if len(events) != 1:
            raise ContractViolation("meta 전 error 뒤에는 이벤트가 올 수 없습니다")
        if events[0]["partial"] is not False:
            raise ContractViolation("meta 전 error는 partial=false여야 합니다")
        return

    if kinds[0] != "meta":
        raise ContractViolation(f"첫 이벤트는 meta 또는 error여야 합니다: {kinds[0]!r}")
    if kinds.count("meta") != 1:
        raise ContractViolation("meta는 정확히 1회여야 합니다 (INV-06)")
    if kinds[-1] not in _TERMINAL:
        raise ContractViolation(f"마지막 이벤트는 done 또는 error여야 합니다: {kinds[-1]!r}")
    if sum(kind in _TERMINAL for kind in kinds) != 1:
        raise ContractViolation("종결 이벤트(done|error)는 정확히 1회여야 합니다 (INV-06)")
    middle = kinds[1:-1]
    if any(kind != "token" for kind in middle):
        raise ContractViolation(f"meta와 종결 이벤트 사이에는 token만 올 수 있습니다: {middle}")

    meta, terminal = events[0], events[-1]
    token_count = len(middle)
    is_compare = "sourceKeyA" in meta

    if is_compare and token_count:
        raise ContractViolation("비교 모드는 token 이벤트가 없습니다 (부록 B.2)")
    if meta.get("noContext") is True:
        if token_count:
            raise ContractViolation("noContext=true 스트림에는 token이 없습니다 (부록 B.1)")
        if terminal["event"] == "done" and terminal["status"] != "NO_CONTEXT":
            raise ContractViolation("noContext=true 스트림의 done.status는 NO_CONTEXT여야 합니다")
    if terminal["event"] == "error" and terminal["partial"] != (token_count > 0):
        raise ContractViolation("error.partial은 token 수신 여부와 같아야 합니다")
    if terminal["event"] == "done" and terminal["status"] == "PARTIAL" and token_count == 0:
        raise ContractViolation("done.status=PARTIAL은 token 1개 이상 수신 후에만 가능합니다")


def load_example(leg: Leg, name: str) -> list[dict[str, Any]]:
    """계약 예시 스트림을 읽는다."""
    path = CONTRACTS_DIR / "examples" / leg / f"{name}.json"
    events: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return events


def example_names(leg: Leg) -> list[str]:
    return sorted(path.stem for path in (CONTRACTS_DIR / "examples" / leg).glob("*.json"))
