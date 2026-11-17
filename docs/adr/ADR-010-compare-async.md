# ADR-010: 비교 모드 비동기 병렬 질의

## Status
Draft

## Date
2026-11-14 (2026-11-17 SSE 계약에 맞춰 Decision 수정)

## Context

비교 모드: 동일 질의에 대해 LangChain v0.3과 v1.x 답변을 나란히 표시하는 기능.

구현 옵션:
- **옵션 A**: 순차 처리 — v0.3 완료 후 v1.x 처리 → 총 latency 2배
- **옵션 B**: `asyncio.gather`로 두 컬렉션 병렬 처리 ✅
- **옵션 C**: 별도 HTTP 요청 2개 (클라이언트 측 병렬) → Spring Boot ↔ FastAPI 연결 복잡도 증가

## Decision

**FastAPI 엔드포인트에서 `asyncio.gather`로 두 컬렉션의 검색을 병렬 실행**하고, 비교 결과는 **토큰 스트리밍 없이 `done` 이벤트에 한 번에 담아** 보낸다.

이벤트 순서와 필드는 `docs/specs/api-spec.md` > 부록 B.2·B.4와 `contracts/sse-events.schema.json`을 따른다.

```
meta (A·B 양측 출처, 인용 번호 A1… / B1…) → done (status: COMPLETED, compareResult)
meta (noContext=true)                      → done (status: NO_CONTEXT)
```

```python
async def compare_stream(req: CompareRequest):
    # 두 버전 검색 병렬 실행 (재작성 질의 1개로 양쪽 검색, ADR-009)
    result_a, result_b = await asyncio.gather(
        retrieve(req.query, source_key=req.source_key_a),
        retrieve(req.query, source_key=req.source_key_b),
    )

    # meta: 양측 출처를 먼저 보낸다 (UI는 결과 전에 출처 카드를 그린다)
    yield meta_event(result_a, result_b)

    # 생성: Structured Outputs로 비교 JSON 1회 생성 → 후처리 검증 (policy §5.6)
    compare_result = await generate_compare(result_a, result_b)

    # done: compareResult를 한 번에 전달. token 이벤트 없음
    yield done_event(status="COMPLETED", compare_result=compare_result)
```

- `token` 이벤트는 비교 모드에서 쓰지 않는다. 계약 스키마의 `token`은 `t` 외 필드를 허용하지 않는다.
- 생성은 OpenAI Structured Outputs(JSON Schema) 1회 호출이다. 버전별 LLM 스트림을 병합하지 않는다.
- `compareResult` 형식과 후처리 규칙(존재하지 않는 인용 제거, 양쪽 인용 없는 변경점 폐기)은 `docs/planning/policy.md` > §5.6을 따른다.

## Consequences

**장점**
- 비교 모드 검색 latency ≈ `max(T_a, T_b)` (순차 대비 ~2배 절감)
- 단일 SSE 연결로 양측 출처와 결과를 받음 → Spring Boot 중계 단순화
- 결과가 검증된 JSON 하나라서 인용 후처리와 저장(`compare_result`)이 단순함

**단점 / 트레이드오프**
- 토큰 스트리밍이 없어 첫 결과 표시까지 기다림이 길다 → `meta`로 출처 카드를 먼저 보여 주고, 비교 첫 이벤트 타임아웃을 30초로 둔다(`UPSTREAM_TIMEOUT`)
- FastAPI 비동기 이벤트 루프 내 CPU bound 작업(임베딩 등) 혼재 시 성능 저하
  → 임베딩은 `asyncio.to_thread`로 오프로드
- JSON 파싱 실패 시 1회 재시도 후 `FAILED(COMPARE_PARSE_ERROR)`

**NO_CONTEXT 처리** (policy §5.6)
- 한쪽만 근거 없음(해당 측 top-1 < τ): 그 측은 `no_evidence: true`로 고정하고 다른 측만 요약한다. 변경점 목록은 만들지 않는다.
- 양쪽 모두 근거 없음: `meta(noContext=true)` → `done(status: NO_CONTEXT, statusReason: LOW_SIMILARITY)`. 생성 LLM을 호출하지 않는다.

**관련 ADR**
- ADR-003: SSE 중계 (비교 모드 SSE 이벤트 포맷)
- ADR-004: 컬렉션 격리 (병렬로 접근할 두 컬렉션)
- ADR-008: NO_CONTEXT (버전별 독립 판단)
- ADR-009: 질의 재작성 (동일 재작성 질의 두 컬렉션에 사용)
