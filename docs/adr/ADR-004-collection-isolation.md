# ADR-004: 버전별 Chroma 컬렉션 물리적 분리

## Status
Accepted

## Date
2026-11-14 (2026-11-17 개정: run 단위 컬렉션·활성 포인터 반영, Accepted)

## Context

LangChain v0.3과 v1.x는 API가 크게 달라 버전 혼입 시 오답이 발생한다. 버전 격리를 구현하는 방법:

| 옵션 | 방식 | 문제 |
|---|---|---|
| 단일 컬렉션 + 메타데이터 필터 | `where={"version": "v0.3"}` | 필터 누락 버그 → 혼입 가능. 소프트 보장 |
| 버전별 별도 컬렉션 | 컬렉션 자체를 분리 | 물리적으로 혼입 불가. 하드 보장 |
| 버전별 별도 Chroma 인스턴스 | 별도 프로세스/포트 | 운영 복잡도 과도 |

인덱스는 "버전 관리되는 빌드 산출물"이다(`docs/planning/policy.md` > §4). 같은 소스라도 재수집·청킹 전략(E2)마다 결과가 달라지므로, 소스당 컬렉션 하나를 덮어쓰면 롤백과 실험 비교가 불가능하다.

## Decision

**수집 실행(run)마다 별도 Chroma 컬렉션**을 만들고, 소스별 활성 run은 `ai.index_pointers`가 가리킨다.

- 컬렉션 이름: `{source_key}_run{ingest_run_id}` (예: `langchain_v03_run12`). run과 컬렉션은 1:1이다.
- 활성 run: `ai.index_pointers(source_key → active_run_id)` 1행. 교체는 트랜잭션으로만 한다(`docs/architecture/db-design.md` > §3.12, INV-01).
- 컬렉션 이름은 코드에 상수로 두지 않는다. 항상 `source_key`와 포인터의 `active_run_id`로 만든다.

```python
def collection_name(source_key: str, run_id: int) -> str:
    return f"{source_key}_run{run_id}"

# 질의 시: 요청의 source_key → index_pointers.active_run_id → 컬렉션
name = collection_name(source_key, pointer.active_run_id)
collection = client.get_collection(name)
```

- 한 질의는 한 컬렉션만 조회한다. 두 소스를 한 번에 조회하는 경로는 없다.
- 컬렉션 분리에 더해, 검색 결과 청크의 `source_key`·`ingest_run_id`가 요청과 다르면 폐기한다(INV-02, 2차 방어).

## Consequences

**장점**
- 버전 혼입이 구조적으로 불가능 — 필터 버그가 없다
- 각 버전 독립 재인덱싱 가능 (v1.x만 다시 빌드 등)
- 직전 run 컬렉션이 남아 있어 1세대 롤백이 포인터 교체만으로 끝난다(`policy.md` > §4.5)
- 청킹 전략 A·B·C를 서로 다른 run으로 만들어 같은 소스에서 비교할 수 있다(E2)
- 평가 지표 E1 (버전 혼입 0건) 달성 근거가 "필터 정확도"가 아닌 "물리적 분리"

**단점 / 트레이드오프**
- 비교 모드에서 두 컬렉션 각각 쿼리 필요 → ADR-010 (비동기 병렬)로 해결
- run마다 컬렉션이 생기므로 정리 규칙이 필요하다. 오래된 SUPERSEDED·FAILED run은 PURGED로 전이하며 컬렉션을 삭제한다(`policy.md` > §4.5)
- 활성 run 조회에 DB 접근이 필요하다 → 30초 포인터 캐시 + reload API로 상쇄

**관련 ADR**
- ADR-005: 오프라인 인덱스 빌드 (run 생성·활성화 명령)
- ADR-010: 비교 모드 비동기 병렬 질의 (두 컬렉션 동시 쿼리)
