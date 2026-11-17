"""근거 부족 sentinel 감지 — 정책서 §5.4 `LLM_ABSTAIN`.

모델은 근거가 부족하면 첫 출력을 `[[NO_ANSWER]]`로 시작한다. 감지하면 토큰을 하나도 내보내지 않는다.
앞 공백을 뺀 앞부분이 sentinel 접두어인 동안만 보류하고(최대 16자), 아니면 즉시 방출한다.
"첫 16자 버퍼링"과 판정 결과는 같고, 일반 답변의 첫 토큰을 늦추지 않는다.
"""

from enum import StrEnum

from src.pipeline.prompts import NO_ANSWER_SENTINEL

BUFFER_LIMIT = 16  # 정책서 §5.4 "첫 16자를 버퍼링"


class GateState(StrEnum):
    PENDING = "PENDING"  # 아직 판정 전 (보류 중)
    PASS = "PASS"  # 일반 답변 — 이후 토큰은 그대로 통과
    ABSTAIN = "ABSTAIN"  # sentinel 감지 — 이후 토큰은 모두 버림


class SentinelGate:
    def __init__(self, sentinel: str = NO_ANSWER_SENTINEL, limit: int = BUFFER_LIMIT) -> None:
        self.sentinel = sentinel
        self.limit = limit
        self.state = GateState.PENDING
        self._buffer = ""

    @property
    def abstained(self) -> bool:
        return self.state is GateState.ABSTAIN

    def feed(self, text: str) -> str:
        """토큰 하나를 넣고 지금 내보낼 텍스트를 돌려준다 (보류·버림이면 빈 문자열)."""
        if self.state is GateState.PASS:
            return text
        if self.state is GateState.ABSTAIN:
            return ""
        self._buffer += text
        head = self._buffer.lstrip()
        if head.startswith(self.sentinel):
            return self._abstain()
        if self.sentinel.startswith(head) and len(self._buffer) < self.limit:
            return ""  # 아직 sentinel일 수 있다
        return self._pass()

    def flush(self) -> str:
        """스트림이 끝났을 때 보류분을 판정한다."""
        if self.state is not GateState.PENDING:
            return ""
        if self._buffer.lstrip().startswith(self.sentinel):
            return self._abstain()
        return self._pass()

    def _abstain(self) -> str:
        self.state = GateState.ABSTAIN
        self._buffer = ""
        return ""

    def _pass(self) -> str:
        self.state = GateState.PASS
        released, self._buffer = self._buffer, ""
        return released
