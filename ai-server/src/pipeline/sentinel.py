"""근거 부족 sentinel 감지 — 정책서 §5.4 `LLM_ABSTAIN`.

근거가 부족하면 모델은 `[[NO_ANSWER]]`만 출력해야 한다. 그래도 기준 버전 머리말
(`{display_name} 기준`, 정책서 §5.5 ③)을 먼저 쓰는 경우가 있어(#108), 앞 공백을 뺀 응답이
① sentinel로 시작하거나 ② 머리말 뒤 공백 다음이 sentinel이면 근거 부족으로 판정한다.
감지하면 토큰을 하나도 내보내지 않는다.

응답 앞부분이 두 형태의 접두어인 동안만 보류하고(최대 머리말 길이 + 16자), 아니면 즉시 방출한다.
일반 답변은 머리말 다음 글자가 나오는 순간 방출되므로 첫 토큰이 머리말 길이만큼만 늦어진다.
"""

from enum import StrEnum

from src.pipeline.prompts import NO_ANSWER_SENTINEL

BUFFER_LIMIT = 16  # 정책서 §5.4 머리말 뒤 보류 한도


class GateState(StrEnum):
    PENDING = "PENDING"  # 아직 판정 전 (보류 중)
    PASS = "PASS"  # 일반 답변 — 이후 토큰은 그대로 통과
    ABSTAIN = "ABSTAIN"  # sentinel 감지 — 이후 토큰은 모두 버림


class SentinelGate:
    def __init__(
        self,
        sentinel: str = NO_ANSWER_SENTINEL,
        limit: int = BUFFER_LIMIT,
        header: str | None = None,
    ) -> None:
        self.sentinel = sentinel
        self.header = header or ""
        self.limit = limit + len(self.header)
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
        verdict = self._judge(self._buffer.lstrip())
        if verdict is GateState.ABSTAIN:
            return self._abstain()
        if verdict is GateState.PENDING and len(self._buffer) < self.limit:
            return ""  # 아직 sentinel일 수 있다
        return self._pass()

    def flush(self) -> str:
        """스트림이 끝났을 때 보류분을 판정한다."""
        if self.state is not GateState.PENDING:
            return ""
        if self._judge(self._buffer.lstrip()) is GateState.ABSTAIN:
            return self._abstain()
        return self._pass()

    def _judge(self, head: str) -> GateState:
        """ABSTAIN = sentinel 확정, PENDING = 아직 sentinel일 수 있음, PASS = 일반 답변."""
        verdict = self._judge_start(head)
        if verdict is not GateState.PASS or not self.header:
            return verdict
        if self.header.startswith(head):
            return GateState.PENDING
        if head.startswith(self.header):
            return self._judge_start(head[len(self.header) :].lstrip())
        return GateState.PASS

    def _judge_start(self, head: str) -> GateState:
        if head.startswith(self.sentinel):
            return GateState.ABSTAIN
        if self.sentinel.startswith(head):
            return GateState.PENDING
        return GateState.PASS

    def _abstain(self) -> str:
        self.state = GateState.ABSTAIN
        self._buffer = ""
        return ""

    def _pass(self) -> str:
        self.state = GateState.PASS
        released, self._buffer = self._buffer, ""
        return released
