# contracts

서비스 간에 공유하는 계약 파일을 둔다. 계약의 원본 설명은 `docs/specs/api-spec.md`이고, 이 디렉터리는 그 내용을 기계가 검증할 수 있는 형식으로 옮긴 것이다.

## SSE 이벤트 계약

| 파일 | 내용 |
| --- | --- |
| `sse-events.schema.json` | `meta`·`token`·`done`·`error` 이벤트 JSON Schema (draft 2020-12) |
| `examples/client/*.json` | backend → 브라우저 구간 예시 스트림 (`POST /api/v1/chat/stream`) |
| `examples/upstream/*.json` | ai-server → backend 구간 예시 스트림 (`POST /internal/v1/chat/stream`) |

- 루트 스키마는 브라우저 구간 이벤트를 검증한다. 내부 구간은 `$defs/upstreamEvent`로 검증한다.
  - 두 구간의 차이는 `meta`의 `conversationId`·`messageId`뿐이다. backend가 중계하면서 추가하고, 게스트는 `null`이다.
- 이벤트 순서 규칙은 스키마가 아니라 계약 테스트가 검사한다.
  - `meta` → `token`* → (`done` | `error`), `meta`와 종결 이벤트는 각각 1회 (`docs/planning/policy.md` > §2.2 > INV-06)
  - `meta` 전 오류는 `error` 단독, `partial=false` (`docs/specs/api-spec.md` > 부록 B.1 > 오류 경로)
- 예시 파일은 SSE `data:` 줄의 JSON을 순서대로 담은 배열이다. `: ping` 하트비트는 포함하지 않는다.

## 계약을 바꿀 때

1. `docs/specs/api-spec.md` > 부록 B를 먼저 고친다.
2. 같은 PR에서 이 디렉터리의 스키마·예시와 양쪽 계약 테스트를 함께 고친다.
   - ai-server: `ai-server/tests/contract/`
   - backend: `backend/contextq/src/test/java/com/r1nn/contextq/contract/`
3. 두 스택의 테스트가 모두 통과해야 병합한다.
