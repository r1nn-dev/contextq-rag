# ADR-008: 유사도 임계값 미만 NO_CONTEXT 반환

## Status
Accepted

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

**코사인 유사도 < τ(source_key) 시 LLM 호출 없이 `NO_CONTEXT` 응답을 반환**한다.

τ는 단일 전역값이 아닌 **source_key별 개별값**으로 관리한다.
source_key마다 문서 도메인·임베딩 분포가 달라 동일 임계값 적용 시 편향이 발생하기 때문이다.

```python
class RAGPipeline:
    def query(self, q: str, source_key: str) -> RAGResponse:
        threshold = self._get_threshold(source_key)
        results = self.retriever.retrieve(q, source_key, top_k=5)

        if not results or results[0].score < threshold:
            return RAGResponse(
                answer=None,
                sources=[],
                status="NO_CONTEXT",
                message="관련 문서를 찾을 수 없습니다. 질문을 구체화하거나 다른 버전을 선택해 주세요."
            )
        return self._generate(q, results)

    def _get_threshold(self, source_key: str) -> float:
        # 환경 변수 TAU_{SOURCE_KEY_UPPER} 가 설정된 경우 yaml 기본값을 오버라이드
        env_key = f"TAU_{source_key.upper()}"
        default = self.config.retrieval.thresholds.get(source_key, 0.5)
        return float(os.getenv(env_key, default))
```

Spring Boot는 `status == "NO_CONTEXT"` 수신 시 SSE `error` 이벤트 없이
UI 전용 메시지를 `done` 이벤트와 함께 전달한다.

τ 기본값은 `configs/rag.yaml`에서 source_key별로 선언한다:

```yaml
retrieval:
  top_k: 5
  thresholds:
    langchain_v03: 0.5   # E1 실험 확정값
    langchain_v1x: 0.5   # E1 실험 확정값
```

운영 환경 오버라이드 (.env):

```dotenv
TAU_LANGCHAIN_V03=0.5
TAU_LANGCHAIN_V1X=0.5
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
- E1 평가 실험(`eval-scenarios.md`) 결과 source_key별 0.5가 precision/recall 균형점으로 확인됨
- `text-embedding-3-small` 모델 기준, 0.5 미만은 도메인 무관 문서 혼입 위험
- source_key 추가 시 E1 동일 프로토콜로 개별 교정 필요

**관련 ADR**
- ADR-003: SSE 중계 (`NO_CONTEXT` 이벤트 흐름)
- ADR-004: 컬렉션 격리 (어느 컬렉션의 유사도인지 명확)
