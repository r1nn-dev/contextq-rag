# ADR-009: 멀티턴 질의 재작성

## Status
Draft

## Date
2026-11-14

## Context

단일 질의(`q = "그 메서드의 반환값은?"`)만으로는 벡터 검색에 필요한 완전한 의미를 담지 못한다.

대화 흐름 예시:
```
턴 1: "AgentExecutor를 어떻게 초기화하나요?"
턴 2: "그 메서드의 반환값은?"        ← "그 메서드"가 무엇인지 컨텍스트 없이 검색 불가
턴 3: "예외 처리는 어떻게 하나요?"   ← 무엇의 예외 처리인지 불명확
```

대안:
- **옵션 A**: 전체 대화 이력을 LLM context로 전달 → 토큰 비용 급증, RAG 검색에 비효율
- **옵션 B**: 직전 N턴 컨텍스트로 현재 질의를 독립적 질의로 재작성 ✅
- **옵션 C**: 재작성 없이 현재 질의만 사용 → 멀티턴 품질 저하

## Decision

**직전 3턴 컨텍스트를 활용하여 현재 질의를 독립적(standalone) 질의로 재작성**한다.

```python
REWRITE_PROMPT = """다음은 대화 이력과 현재 질문입니다.
현재 질문이 대화 맥락 없이도 의미가 명확한 독립적인 질문이 되도록 재작성하세요.
질문의 의미만 명확히 하고, 답변은 포함하지 마세요.

대화 이력:
{history}

현재 질문: {question}

재작성된 질문:"""

class QueryRewriter:
    def rewrite(
        self,
        question: str,
        history: list[tuple[str, str]],  # [(user_msg, assistant_msg), ...]
        max_turns: int = 3
    ) -> str:
        recent = history[-max_turns:]
        if not recent:
            return question  # 첫 턴: 재작성 불필요

        history_text = "\n".join(
            f"사용자: {u}\n어시스턴트: {a}"
            for u, a in recent
        )
        return self.llm.invoke(
            REWRITE_PROMPT.format(history=history_text, question=question)
        )
```

재작성된 질의는 RAG 검색에만 사용하고, 사용자에게 표시되는 메시지는 원본 질의를 유지한다.

## Consequences

**장점**
- 대명사·지시어가 포함된 멀티턴 질의에서도 벡터 검색 품질 유지
- 검색 단계에서만 재작성 — 답변 생성용 LLM 프롬프트는 별도 관리

**단점 / 트레이드오프**
- 재작성 LLM 호출 추가 → 첫 번째 턴 이후 모든 질의에 latency 추가 (~500ms)
- 재작성 실패(LLM이 의미를 왜곡) 시 검색 품질 저하 가능
- max_turns=3: 짧은 컨텍스트 창 → 긴 대화에서 초반 맥락 소실

**max_turns=3 선정 근거**
- 기술 문서 Q&A 도메인 특성상 주제 전환이 잦아 과거 맥락이 오히려 노이즈
- LLM 호출 비용(토큰) 최소화
- 평가 시나리오에서 3턴이 품질 대비 비용 최적점으로 판단

**관련 ADR**
- ADR-008: NO_CONTEXT (재작성 후 검색 → 임계값 판단)
- ADR-010: 비교 모드 (두 컬렉션에 동일하게 재작성 질의 사용)
