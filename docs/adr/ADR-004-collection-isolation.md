# ADR-004: 버전별 Chroma 컬렉션 물리적 분리

## Status
Draft

## Date
2026-11-14

## Context

LangChain v0.3과 v1.x는 API가 크게 달라 버전 혼입 시 오답이 발생한다. 버전 격리를 구현하는 방법:

| 옵션 | 방식 | 문제 |
|---|---|---|
| 단일 컬렉션 + 메타데이터 필터 | `where={"version": "v0.3"}` | 필터 누락 버그 → 혼입 가능. 소프트 보장 |
| 버전별 별도 컬렉션 | 컬렉션 자체를 분리 | 물리적으로 혼입 불가. 하드 보장 |
| 버전별 별도 Chroma 인스턴스 | 별도 프로세스/포트 | 운영 복잡도 과도 |

## Decision

**버전별 별도 Chroma 컬렉션**을 사용한다.

```python
# 컬렉션 이름 규칙
COLLECTION_V03 = "langchain_v03"
COLLECTION_V1X = "langchain_v1x"

col_v03 = client.get_or_create_collection("langchain_v03")
col_v1x = client.get_or_create_collection("langchain_v1x")
```

질의 시 버전 파라미터가 컬렉션 이름을 직접 결정한다:

```python
def get_collection(version: Literal["v0.3", "v1.x"]) -> chromadb.Collection:
    name = "langchain_v03" if version == "v0.3" else "langchain_v1x"
    return client.get_collection(name)
```

## Consequences

**장점**
- 버전 혼입이 구조적으로 불가능 — 필터 버그가 없다
- 각 버전 독립 재인덱싱 가능 (v1.x만 다시 빌드 등)
- 평가 지표 E1 (버전 혼입 0건) 달성 근거가 "필터 정확도"가 아닌 "물리적 분리"

**단점 / 트레이드오프**
- 비교 모드에서 두 컬렉션 각각 쿼리 필요 → ADR-010 (비동기 병렬)로 해결
- 버전이 늘어날수록 컬렉션 수 증가 (현재 2개 — 범위 내)

**관련 ADR**
- ADR-010: 비교 모드 비동기 병렬 질의 (두 컬렉션 동시 쿼리)
