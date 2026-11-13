# ADR-003: 스트리밍 전송 방식 — SSE + fetch ReadableStream

## Status
Draft

## Date
2026-11-14

## Context

LLM 답변은 토큰 단위로 생성되므로 스트리밍이 필요하다. 옵션을 검토했다:

| 옵션 | 특징 | 단점 |
|---|---|---|
| WebSocket | 양방향, 연결 유지 | 오버헤드 큼, 단방향 스트리밍에 과도 |
| SSE (Server-Sent Events) | 단방향, HTTP 기반, 자동 재연결 | 단방향 전용 |
| Polling | 구현 단순 | 레이턴시, 서버 부하 |
| gRPC streaming | 성능 우수 | 브라우저 직접 지원 없음 |

**아키텍처 고려사항**: ADR-001 이중 서버 구조에서 스트리밍 경로는 두 가지다.
- **방식 X**: Frontend → Spring Boot → FastAPI (Spring Boot가 SSE 중계)
- **방식 Y**: Frontend → FastAPI 직접 (인증 우회 문제)

## Decision

**SSE + fetch ReadableStream**, 경로는 **방식 X** (Spring Boot 중계)를 채택한다.

```
Frontend (fetch + ReadableStream)
  → Spring Boot /api/chat/stream (인증 · 쿼터 검사)
    → FastAPI /internal/rag/stream (SSE)
      → LLM API (토큰 스트리밍)
```

Spring Boot는 FastAPI의 SSE를 받아 `SseEmitter`로 Frontend에 중계.

**이벤트 타입 정의**:
```
event: meta   → 출처 목록 (sources[]) — 답변 생성 전 전송
event: token  → LLM 토큰 조각
event: done   → 스트림 종료
event: error  → 오류 메시지
```

## Consequences

**장점**
- 모든 요청이 Spring Boot를 통과 → JWT 검증·쿼터 차감 단일 지점 처리
- SSE는 HTTP/1.1 호환, 추가 프로토콜 불필요
- `meta` 이벤트로 출처를 답변 전에 먼저 렌더링 가능 (UI UX 개선)

**단점 / 트레이드오프**
- Spring Boot가 SSE를 중계하는 복잡성 추가 (`SseEmitter` + 비동기 처리)
- 연결 중단 시 Spring Boot ↔ FastAPI 양쪽 연결 모두 정리 필요

**관련 ADR**
- ADR-001: 이중 서버 구조 (중계 경로 근거)
