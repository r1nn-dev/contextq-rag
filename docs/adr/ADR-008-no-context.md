# ADR-008: 유사도 임계값 미만 NO_CONTEXT 반환

## Status
Draft

## Date
2026-11-14

## Context

RAG 시스템에서 LLM 할루시네이션 억제 요건:

- 질의와 무관한 문서가 검색되어도 LLM은 답변을 생성함
- 코사인 유사도가 낮은 결과로 답변 생성 시 오히려 신뢰성 저하
- LLM 호출 비용(latency + API cost) 불필요하게 소모

대안:
- **옵션 A**: 임계값 미만 시 LLM에게 "컨텍스트 없음"을 명시 → prompt injection 위험, 여전히 LLM 호출
- **옵션 B**: 임계값 미만 시 LLM 호출 없이 고정 응답 반환 ✅
- **옵션 C**: 임계값 없이 항상 LLM 호출 → 할루시네이션 위험 높음

## Decision

**코사인 유사도 < τ (기본값 0.72) 시 LLM 호출 없이 `NO_CONTEXT` 응답을 반환**한다.

```python
NO_CONTEXT_THRESHOLD = 0.72  # configs/rag.yaml 에서 override 가능

class RAGPipeline:
    def query(self, q: str, version: str) -> RAGResponse:
        results = self.retriever.retrieve(q, version, top_k=5)

        if not results or results[0].score < NO_CONTEXT_THRESHOLD:
            return RAGResponse(
                answer=None,
                sources=[],
                status="NO_CONTEXT",
                message="관련 문서를 찾을 수 없습니다. 질문을 구체화하거나 다른 버전을 선택해 주세요."
            )

        # 임계값 이상: LLM 호출
        return self._generate(q, results)
```

Spring Boot는 `status == "NO_CONTEXT"` 수신 시 SSE `error` 이벤트 없이
UI 전용 메시지를 `done` 이벤트와 함께 전달한다.

τ 값은 `configs/rag.yaml`에서 조정 가능:

```yaml
retrieval:
  top_k: 5
  no_context_threshold: 0.72
```

## Consequences

**장점**
- LLM 호출 없이 빠른 응답 (< 50ms)
- 할루시네이션 구조적 차단 — 근거 없는 답변 생성 불가
- 운영 비용 절감 (LLM API 호출 감소)

**단점 / 트레이드오프**
- τ 값이 너무 높으면 정상 질의도 NO_CONTEXT → 사용자 경험 저하
- τ 값이 너무 낮으면 무관한 문서로 답변 생성 → 초기 조정 필요
- 임계값은 임베딩 모델 교체 시 재교정 필요

**τ 선정 근거**
- `text-embedding-3-small` 모델 기준, LangChain 문서 도메인 내 실험적 최솟값
- R-1 단계에서 평가 시나리오(`eval-scenarios.md`)로 검증 예정

**관련 ADR**
- ADR-003: SSE 중계 (`NO_CONTEXT` 이벤트 흐름)
- ADR-004: 컬렉션 격리 (어느 컬렉션의 유사도인지 명확)
