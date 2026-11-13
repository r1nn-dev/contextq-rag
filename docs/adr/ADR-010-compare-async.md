# ADR-010: 비교 모드 비동기 병렬 질의

## Status
Draft

## Date
2026-11-14

## Context

비교 모드: 동일 질의에 대해 LangChain v0.3과 v1.x 답변을 나란히 표시하는 기능.

구현 옵션:
- **옵션 A**: 순차 처리 — v0.3 완료 후 v1.x 처리 → 총 latency 2배
- **옵션 B**: `asyncio.gather`로 두 컬렉션 병렬 처리 ✅
- **옵션 C**: 별도 HTTP 요청 2개 (클라이언트 측 병렬) → Spring Boot ↔ FastAPI 연결 복잡도 증가

## Decision

**FastAPI 엔드포인트에서 `asyncio.gather`로 두 컬렉션 RAG 파이프라인을 병렬 실행**한다.

```python
@router.post("/query/compare")
async def compare_query(req: CompareRequest) -> StreamingResponse:
    async def stream():
        # 두 버전 병렬 실행
        v03_task = asyncio.create_task(
            pipeline.aquery(req.question, version="v0.3", history=req.history)
        )
        v1x_task = asyncio.create_task(
            pipeline.aquery(req.question, version="v1.x", history=req.history)
        )

        v03_result, v1x_result = await asyncio.gather(v03_task, v1x_task)

        # SSE: meta 이벤트 (두 버전 출처 함께 전송)
        yield f"event: meta\ndata: {json.dumps({'v03': v03_result.sources, 'v1x': v1x_result.sources})}\n\n"

        # SSE: 토큰 스트리밍 (두 LLM 스트림 인터리브)
        async for chunk in merge_streams(v03_result.stream, v1x_result.stream):
            yield f"event: token\ndata: {chunk}\n\n"

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
```

스트림 병합 전략:
- 두 LLM 스트림을 `asyncio.Queue`로 인터리브
- 각 토큰에 `version` 필드 포함 (`{"version": "v0.3", "token": "..."}`)
- 프론트엔드는 `version` 필드로 좌/우 패널 구분

## Consequences

**장점**
- 비교 모드 총 latency ≈ `max(T_v03, T_v1x)` (순차 대비 ~2배 절감)
- 단일 SSE 연결로 두 버전 답변 수신 → Spring Boot 중계 단순화

**단점 / 트레이드오프**
- FastAPI 비동기 이벤트 루프 내 CPU bound 작업(임베딩 등) 혼재 시 성능 저하
  → 임베딩은 `asyncio.to_thread`로 오프로드
- 한 버전이 `NO_CONTEXT`인 경우 처리 로직 추가 필요
- 에러 격리: 한 버전 실패 시 나머지 버전 결과는 정상 반환

**NO_CONTEXT 처리**
```python
# 한 버전만 NO_CONTEXT인 경우 해당 패널에 메시지 표시, 나머지는 정상 출력
if v03_result.status == "NO_CONTEXT":
    yield f"event: token\ndata: {json.dumps({'version': 'v0.3', 'no_context': True})}\n\n"
```

**관련 ADR**
- ADR-003: SSE 중계 (비교 모드 SSE 이벤트 포맷)
- ADR-004: 컬렉션 격리 (병렬로 접근할 두 컬렉션)
- ADR-008: NO_CONTEXT (버전별 독립 판단)
- ADR-009: 질의 재작성 (동일 재작성 질의 두 컬렉션에 사용)
