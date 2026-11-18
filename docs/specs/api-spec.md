# API 명세서

> 최종 수정일: 2026-11-18

---

## 0. 공통 규약

### 0.1 기본 규칙

| 항목 | 값 |
| --- | --- |
| Base URL | `/api/v1` |
| 인증 방식 | `Authorization: Bearer {accessToken}` (JWT HS256). Spring Security 직접 검증 |
| 요청 추적 | nginx가 `X-Request-Id` (UUID v4) 발급 → backend → ai-server 전파. 로그·오류·메시지 전 구간 포함 |
| Content-Type | `application/json; charset=UTF-8` (SSE 제외) |
| 경로 규칙 | 영문 소문자 복수형, kebab-case |
| 날짜·시각 | ISO 8601 UTC. 예: `2026-10-01T10:15:30Z`. DB는 `TIMESTAMPTZ(6)` |
| 버전 | 하위 호환 불가 변경 시에만 `/api/v2` 추가 |

---

### 0.2 식별자(ID) 규칙

| 식별자 | 타입 | 비고 |
| --- | --- | --- |
| 도메인 PK (`id`) | 정수 (BIGINT) | URL 경로·JSON 모두 숫자 |
| `source_key` | 문자열 VARCHAR(50) | 예: `"langchain_v03"` |
| `request_id` / `X-Request-Id` | UUID v4 문자열 36자 | 전 구간 전파 |
| Refresh Token (쿠키) | 불투명 256비트 Base64URL | DB에는 SHA-256 해시만 저장 |

---

### 0.3 공통 성공·에러 응답

```jsonc
// ① 단건 조회 성공
{ "success": true, "message": null, "data": { /* 리소스 */ } }

// ② 작업 성공
{ "success": true, "message": "로그아웃되었습니다.", "data": null }

// ③ 커서 기반 목록 조회 성공
{
  "success": true,
  "message": null,
  "data": {
    "items": [ /* ... */ ],
    "cursor": "2026-10-01T09:00:00Z",
    "hasNext": true
  }
}

// ④ 비즈니스 오류
{
  "success": false,
  "error": {
    "code": "AUTH_LOCKED",
    "message": "로그인 시도 초과. 15분 후 다시 시도해주세요.",
    "details": []
  }
}

// ⑤ 입력 검증 실패
{
  "success": false,
  "error": {
    "code": "INVALID_REQUEST",
    "message": "입력값을 확인해주세요.",
    "details": [
      { "field": "email",    "reason": "올바른 이메일 형식이 아닙니다." },
      { "field": "password", "reason": "8~64자, 영문·숫자 각 1자 이상이어야 합니다." }
    ]
  }
}
```

**Spring Boot 응답 타입 규약**

| 경우 | 반환 타입 |
| --- | --- |
| 단건·작업 | `ResponseEntity<ApiResponse<T>>` |
| 커서 목록 | `ResponseEntity<ApiResponse<CursorResponse<T>>>` |
| SSE 스트리밍 | `Flux<ServerSentEvent<String>>` (`text/event-stream`) |
| 스트림 시작 전 오류 | `ResponseEntity<ApiResponse<Void>>` (일반 JSON) |

```java
// CursorResponse<T>
record CursorResponse<T>(
    List<T> items,
    String  cursor,   // ISO 8601. 마지막 페이지이면 null
    boolean hasNext
) {}
```

---

### 0.4 에러 코드 표

접두어 = 담당 도메인.

| 코드 | HTTP | 도메인 | 발생 조건 |
| --- | --- | --- | --- |
| `INVALID_REQUEST` | 400 | 공통 | Bean Validation 실패·해석할 수 없는 요청 본문. `details[]`에 필드별 사유 포함. 없는 경로(404)·허용되지 않는 메서드(405)도 이 코드를 쓰고 HTTP 상태만 다르다 |
| `AUTH_INVALID_CREDENTIALS` | 401 | Auth | 로그인 실패 (미존재 계정도 더미 BCrypt 수행, 시간차 제거) |
| `AUTH_TOKEN_MISSING` | 401 | Auth | Authorization 헤더 없음 |
| `AUTH_TOKEN_INVALID` | 401 | Auth | JWT 서명 오류·형식 불일치 |
| `AUTH_TOKEN_EXPIRED` | 401 | Auth | Access Token 만료 → silent refresh 후 재시도 |
| `AUTH_REFRESH_MISSING` | 401 | Auth | Refresh Token 쿠키 없음 |
| `AUTH_REFRESH_INVALID` | 401 | Auth | Refresh Token DB 미존재 |
| `AUTH_REFRESH_EXPIRED` | 401 | Auth | 패밀리 7일 절대 만료 |
| `AUTH_REFRESH_REUSED` | 401 | Auth | USED 토큰 5초 유예 이후 재제출 → 패밀리 전체 REVOKED |
| `FORBIDDEN` | 403 | Auth | 비관리자 `/admin/**` 접근 |
| `FORBIDDEN_IN_PROFILE` | 403 | Auth | prod 환경 재수집 트리거 호출 |
| `GUEST_MODE_NOT_ALLOWED` | 403 | Guest | 게스트 COMPARE 모드 시도 |
| `CONVERSATION_NOT_FOUND` | 404 | Conv | 없는 대화 또는 타인 대화 (INV-14, 소유자 여부 미노출) |
| `USER_NOT_FOUND` | 404 | Admin | 관리자 계정 잠금 해제 대상 사용자 없음 (§5.4) |
| `SOURCE_NOT_FOUND` | 404 | Index | `source_key` 미존재 |
| `AUTH_REFRESH_CONFLICT` | 409 | Auth | USED 토큰 5초 유예 내 재제출 → 1회 재시도 |
| `CONVERSATION_BUSY` | 409 | Conv | 진행 중 ASSISTANT 메시지 존재 (INV-11) |
| `CONVERSATION_FULL` | 409 | Conv | 메시지 100개 도달 |
| `SOURCE_UNAVAILABLE` | 409 | Conv | 비활성 버전으로 질문 |
| `AUTH_LOCKED` | 429 | Auth | 5회 실패 잠금. `Retry-After` 포함 |
| `GUEST_QUOTA_EXCEEDED` | 429 | Guest | 게스트 5회 소진 |
| `GUEST_SESSION_LIMIT` | 429 | Guest | IP당 신규 세션 30개/시간 초과 |
| `RATE_LIMITED` | 429 | 공통 | 분당 한도 초과. `Retry-After` 포함 |
| `DAILY_QUOTA_EXCEEDED` | 429 | Conv | 일일 100회 초과 |
| `CONCURRENT_STREAM_LIMIT` | 429 | Conv | 동시 스트림 초과 |
| `EMBEDDING_MODEL_MISMATCH` | 500 | Index | INV-03 위반 (관리자 알림) |
| `LLM_ERROR` | 502 | AI | OpenAI API 오류 |
| `COMPARE_PARSE_ERROR` | 502 | AI | 비교 JSON 파싱 2회 실패 |
| `AI_UNAVAILABLE` | 503 | AI | ai-server 연결 실패 |
| `AI_BUSY` | 503 | AI | 동시 생성 20 초과 (즉시 거절) |
| `INDEX_NOT_ACTIVE` | 503 | Index | ACTIVE run 없음 (INV-01 위반, 장애) |
| `INTERNAL_UNAUTHORIZED` | 401 | AI | ai-server 내부 API `X-Internal-Token` 누락·불일치 (backend 설정 오류, 브라우저에는 `AI_UNAVAILABLE`로 전달) |
| `INTERNAL_ERROR` | 500 | 공통 | backend 예기치 않은 오류(스택 트레이스 미노출, 서버 로그에 `X-Request-Id`와 함께 원인 기록). ai-server의 같은 코드는 스트림 전후 모두 브라우저에 `AI_UNAVAILABLE`로 전달 |
| `UPSTREAM_TIMEOUT` | 504 | AI | 첫 이벤트 15초·비교 30초 초과 |

---

### 0.5 상태값 요약

| 도메인(테이블) | 컬럼 | 상태값 |
| --- | --- | --- |
| `app.users` | status | `ACTIVE` / `LOCKED` |
| `app.token_families` | status | `ACTIVE` / `REVOKED` |
| `app.refresh_tokens` | status | `ACTIVE` / `USED` / `REVOKED` |
| `app.guest_sessions` | status | `ACTIVE` / `EXHAUSTED` |
| `app.conversations` | status (파생·미저장) | `OPEN` / `READ_ONLY` |
| `app.messages` (ASSISTANT) | status | `PENDING` / `STREAMING` / `PROCESSING` / `COMPLETED` / `PARTIAL` / `NO_CONTEXT` / `FAILED` |
| `ai.ingest_runs` | status | `PENDING` / `COLLECTING` / `PROCESSING` / `EMBEDDING` / `VALIDATING` / `READY` / `ACTIVE` / `RESTORING` / `SUPERSEDED` / `PURGED` / `FAILED` |

> **`ai.ingest_runs` 상태 설계 원칙:** 검증 통과(`READY`)와 서비스 반영(`ACTIVE`)을 분리하여 품질 불량 인덱스를 라이브 반영 전에 차단할 수 있도록 한다. `READY` → `ACTIVE` 전환은 관리자 명시적 명령(`make activate-index`)으로만 가능. `RESTORING`은 S3 스냅샷 복원 경로의 별도 진입점.

---

### 0.6 권한 매트릭스

| API 그룹 | 게스트 | ROLE\_USER | ROLE\_ADMIN |
| --- | --- | --- | --- |
| `POST /auth/signup`, `POST /auth/login` | ✅ | ✅ | ✅ |
| `POST /auth/refresh`, `POST /auth/logout` | ✅ (쿠키) | ✅ | ✅ |
| `GET /auth/me` | ❌ 401 | ✅ | ✅ |
| `GET /sources` | ✅ | ✅ | ✅ |
| `POST /chat/stream` SINGLE | ✅ 5회 한도 | ✅ | ✅ |
| `POST /chat/stream` COMPARE | ❌ 403 | ✅ | ✅ |
| `GET /conversations`, `GET /conversations/{id}` | ❌ 401 | ✅ 본인만 | ✅ 본인만 |
| `GET /admin/**` | ❌ 401 | ❌ 403 | ✅ |
| `POST /admin/index/ingest/{key}` P2 | ❌ | ❌ | ✅ local·staging 전용 |
| `/internal/v1/**` (ai-server) | 내부망 전용 (외부 불가) |  |  |

---

### 0.7 Rate Limit 정책

**nginx 계층 (IP 기준)**

| 경로 | 한도 | Burst | 전시회 11/18 |
| --- | --- | --- | --- |
| `/api/v1/auth/**` | 10 req/분 | 5 | 동일 |
| `/api/v1/chat/**` | 30 req/분 | 10 | 60 / burst 20 |
| 그 외 `/api/**` | 120 req/분 | 30 | 동일 |

**backend 계층 (사용자·세션 기준)**

| 대상 | 한도 | 저장소 | 초과 코드 |
| --- | --- | --- | --- |
| 게스트 세션 | 5회 / 24h | PostgreSQL | `GUEST_QUOTA_EXCEEDED` |
| 게스트 IP당 신규 세션 | 30개/h (전시 60) | PostgreSQL | `GUEST_SESSION_LIMIT` |
| 로그인 사용자 분당 | 10 질문 | 메모리 토큰 버킷 | `RATE_LIMITED` + `Retry-After` |
| 로그인 사용자 일일 | 100 질문 (COMPARE=2, KST 00:00 초기화) | messages COUNT | `DAILY_QUOTA_EXCEEDED` |
| 동시 스트림 | 사용자당 2 / 게스트당 1 | 메모리 카운터 | `CONCURRENT_STREAM_LIMIT` |

**ai-server 계층 (전체)**

| 한도 | 초과 코드 |
| --- | --- |
| 동시 생성 20 (asyncio Semaphore, E6 후 확정) | `AI_BUSY` 503, 즉시 거절 |

---

### 0.8 API 작성 템플릿

```text
### N.N {기능명}
- **Method / URI**: METHOD /api/v1/path
- **서비스**: backend (Spring Boot) | ai-server (FastAPI)
- **인증**: 불필요 | JWT | JWT+ADMIN | 게스트 쿠키
- **Rate Limit**: nginx 계층 | backend 계층 | 없음
- **Idempotency**: 멱등 | 비멱등
- **대응 테이블**: schema.table_name
- **설명**: 한 줄 요약
- **요청 파라미터**: (없으면 생략)
- **요청 헤더**: (특수 헤더만. 없으면 생략)
- **요청 바디**: JSON 예시
- **응답 (HTTP 코드)**:
- **에러**: `CODE`(HTTP) — 발생 조건
- **프론트 계약**: (필요 시)
- **동시성·멱등 보장**: (필요 시)
```

> 에러 코드: HTTP 오름차순 → 같은 코드 내 흐름순. 신규 추가 시 0.4 + 0.6 함께 갱신 (PR 체크리스트)

## 1. 인증 (Auth)

> **서비스**: backend (Spring Boot)\
**대응 테이블**: `app.users`, `app.token_families`, `app.refresh_tokens`\
**Rate Limit**: nginx `/api/v1/auth/**` 10 req/분 (burst 5)

---

### 1.1 회원가입

- **Method / URI**: `POST /api/v1/auth/signup`
- **인증**: 불필요
- **Idempotency**: 비멱등 (이메일 중복 시 400)
- **설명**: 이메일·비밀번호로 계정 생성. `ROLE_USER` 고정. 관리자는 환경 변수 시드로만 생성.

**요청 바디**

```json
{
  "email":    "user@example.com",
  "password": "pass1234"
}
```

| 필드 | 타입 | 제약 |
| --- | --- | --- |
| email | string | 최대 254자. `@` 1개, 도메인에 `.` 포함. 소문자 정규화·앞뒤 공백 제거 후 저장 |
| password | string | 8\~64자, 영문 1자 이상·숫자 1자 이상. 이메일과 동일 금지 |

**응답 201**

```json
{
  "success": true,
  "message": "회원가입이 완료되었습니다.",
  "data": { "userId": 12 }
}
```

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | 필드 검증 실패 (`details[]` 포함) |
| `INVALID_REQUEST` | 400 | 이메일이 이미 존재함 (`field: "email"`, `reason: "이미 사용 중인 이메일입니다."`) |

---

### 1.2 로그인

- **Method / URI**: `POST /api/v1/auth/login`
- **인증**: 불필요
- **Idempotency**: 비멱등
- **설명**: 이메일·비밀번호 검증 후 Access Token(응답 바디)·Refresh Token(HttpOnly 쿠키) 발급. 로그인 성공 시 실패 카운트 0 초기화.

**요청 바디**

```json
{
  "email":    "user@example.com",
  "password": "pass1234"
}
```

**응답 200**

```json
{
  "success": true,
  "message": null,
  "data": {
    "accessToken": "<ACCESS_TOKEN>",
    "tokenType":   "Bearer",
    "expiresIn":   1800
  }
}
```

**Set-Cookie (응답 헤더)**

```
Set-Cookie: devdocs_rt=<REFRESH_TOKEN>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=604800
```

| 필드 | 설명 |
| --- | --- |
| `accessToken` | JWT HS256, 30분 유효. 클라이언트는 **메모리에만 보관** (localStorage 금지) |
| `expiresIn` | 초 단위 만료 시간 (1800) |
| `devdocs_rt` 쿠키 | 256비트 불투명 난수. DB에는 SHA-256 해시만 저장. 패밀리 만료 7일 절대 |

**Access Token 클레임**

```jsonc
{
  "sub":  "12",             // user_id
  "role": "ROLE_USER",
  "iat":  1727776530,
  "exp":  1727778330,
  "jti":  "uuid-v4"
}
```

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | 필드 누락·형식 오류 |
| `AUTH_INVALID_CREDENTIALS` | 401 | 이메일·비밀번호 불일치 (계정 존재 여부 미노출) |
| `AUTH_LOCKED` | 429 | 15분 내 5회 실패. `Retry-After: 900` 포함 |

**동시성 보장**

- 미존재 계정에도 더미 BCrypt 비교 수행 → 응답 시간 차이로 계정 존재 여부 추론 차단.
- 사용자당 ACTIVE 패밀리 최대 10개. 초과 시 가장 오래된 패밀리 REVOKED 후 신규 발급.

---

### 1.3 토큰 갱신 (Refresh)

- **Method / URI**: `POST /api/v1/auth/refresh`
- **인증**: 게스트 쿠키 (`devdocs_rt` HttpOnly 쿠키 자동 첨부)
- **Idempotency**: 비멱등 (매 호출마다 새 토큰 발급)
- **설명**: Refresh Token 회전. 기존 토큰 USED 처리 + 신규 토큰 ACTIVE 발급을 단일 트랜잭션으로 처리 (INV-15).

**요청**: 바디 없음. `devdocs_rt` 쿠키 자동 첨부.

**응답 200**

```json
{
  "success": true,
  "message": null,
  "data": {
    "accessToken": "<ACCESS_TOKEN>",
    "tokenType":   "Bearer",
    "expiresIn":   1800
  }
}
```

Set-Cookie: 신규 `devdocs_rt` 발급 (기존과 동일 속성).

**에러**

| 코드 | HTTP | 조건 | 클라이언트 처리 |
| --- | --- | --- | --- |
| `AUTH_REFRESH_MISSING` | 401 | 쿠키 없음 | 로그인 화면 |
| `AUTH_REFRESH_INVALID` | 401 | DB 미존재, 또는 로그아웃·초과 정리로 이미 폐기(REVOKED)된 토큰·패밀리 | 로그인 화면 |
| `AUTH_REFRESH_EXPIRED` | 401 | 패밀리 7일 만료 | 로그인 화면 |
| `AUTH_REFRESH_REUSED` | 401 | 5초 유예 이후 USED 재제출 → 패밀리 전체 REVOKED | "보안을 위해 로그아웃되었습니다" |
| `AUTH_REFRESH_CONFLICT` | 409 | 5초 유예 내 재제출 (다중 탭 경합) | 1회 재시도 (단일 Promise 직렬화) |

**동시성 보장**

- 유예 5초 이내 USED 토큰 재제출 → `AUTH_REFRESH_CONFLICT`(409). 브라우저 쿠키는 이미 새 토큰이므로 1회 재시도하면 성공.
- 5초 초과 USED 재제출 → 탈취로 간주, 패밀리 전체 REVOKED, 쿠키 `Max-Age=0` 삭제.
- `AUTH_REFRESH_INVALID`·`AUTH_REFRESH_EXPIRED`·`AUTH_REFRESH_REUSED` 응답은 쓸 수 없는 쿠키를 지우도록 `Set-Cookie: devdocs_rt=; Max-Age=0`을 함께 보낸다. `AUTH_REFRESH_CONFLICT`는 쿠키를 건드리지 않는다(브라우저 쿠키가 이미 새 토큰).

---

### 1.4 로그아웃

- **Method / URI**: `POST /api/v1/auth/logout`
- **인증**: 불필요 (쿠키만 있으면 처리. Access Token 없어도 동작)
- **Idempotency**: 멱등
- **설명**: 현재 패밀리 REVOKED. 쿠키 `Max-Age=0`. 이미 발급된 Access Token은 만료(최대 30분)까지 유효 — 무상태 검증의 트레이드오프로 문서화.

**요청**: 바디 없음.

**응답 200**

```json
{
  "success": true,
  "message": "로그아웃되었습니다.",
  "data": null
}
```

Set-Cookie: `devdocs_rt=; Max-Age=0; Path=/api/v1/auth; HttpOnly; Secure; SameSite=Strict`

**에러**: 쿠키 없거나 이미 REVOKED여도 200 반환 (멱등).

---

### 1.5 내 정보 조회

- **Method / URI**: `GET /api/v1/auth/me`
- **인증**: JWT 필수
- **Idempotency**: 멱등
- **설명**: Access Token의 `sub` 클레임으로 사용자 정보 조회. 토큰 갱신 없이 UI 초기화에 사용.

**응답 200**

```json
{
  "success": true,
  "message": null,
  "data": {
    "userId":    12,
    "email":     "user@example.com",
    "role":      "ROLE_USER",
    "createdAt": "2026-10-01T10:15:30Z"
  }
}
```

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `AUTH_TOKEN_MISSING` | 401 | Authorization 헤더 없음 |
| `AUTH_TOKEN_INVALID` | 401 | JWT 서명 오류·형식 불일치 |
| `AUTH_TOKEN_EXPIRED` | 401 | Access Token 만료 → 클라이언트 silent refresh 후 재시도 |

## 2. 소스 메타 (Sources)

> **서비스**: backend (Spring Boot)\
**데이터 출처**: ai-server `GET /internal/v1/sources` (6.3). backend는 ai 스키마 테이블을 직접 읽지 않는다\
**캐시**: 60초 서버 캐시

---

### 2.1 소스 목록 조회

- **Method / URI**: `GET /api/v1/sources`
- **인증**: 불필요
- **Idempotency**: 멱등
- **설명**: UI 초기화 시 질문 가능한 소스 버전 목록과 비교 가능 쌍을 반환한다. `enabled=true` AND ACTIVE run 존재인 소스만 포함. `compare_enabled`는 DB 컬럼이 아니라 런타임 계산값.

**응답 200**

```json
{
  "success": true,
  "message": null,
  "data": {
    "sources": [
      {
        "sourceKey":    "langchain_v03",
        "framework":    "langchain",
        "versionLabel": "v0.3",
        "displayName":  "LangChain v0.3",
        "enabled":      true,
        "activeRun": {
          "commitSha":   "<COMMIT_SHA_A>",
          "ingestedAt":  "2026-10-05",
          "chunkCount":  3842
        }
      },
      {
        "sourceKey":    "langchain_v1x",
        "framework":    "langchain",
        "versionLabel": "v1.x",
        "displayName":  "LangChain v1.x",
        "enabled":      true,
        "activeRun": {
          "commitSha":   "<COMMIT_SHA_B>",
          "ingestedAt":  "2026-10-05",
          "chunkCount":  5120
        }
      }
    ],
    "comparePairs": [
      {
        "compareEnabled": true,
        "sourceKeyA":     "langchain_v03",
        "sourceKeyB":     "langchain_v1x"
      }
    ],
    "guest": {
      "limit":     5,
      "used":      2,
      "remaining": 3,
      "expiresAt": "2026-10-02T10:15:30Z"
    }
  }
}
```

| 필드 | 설명 |
| --- | --- |
| `sources[]` | enabled=true AND ACTIVE run 존재 소스만 포함 |
| `guest` | 로그인하지 않은 요청의 게스트 이용 현황. 유효한 Access Token이 있으면 `null` (정책서 §1.3) |
| `guest.limit` | 세션당 질문 한도 (5) |
| `guest.used` / `guest.remaining` | `devdocs_sid` 쿠키 세션의 사용 횟수 / `limit - used`. 쿠키가 없거나 세션이 만료·미존재면 `used` 0, `remaining` 5 |
| `guest.expiresAt` | 세션 절대 만료 시각(ISO 8601 UTC). 쿠키가 없거나 만료면 `null`. 이 API는 게스트 쿠키를 발급하지 않는다(최초 질문 시 발급) |
| `activeRun.ingestedAt` | YYYY-MM-DD (UTC 기준 수집 완료일) |
| `comparePairs[].compareEnabled` | 양측 소스가 모두 enabled=true AND ACTIVE run 존재일 때 true |

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INDEX_NOT_ACTIVE` | 503 | enabled 소스가 존재하나 ACTIVE run이 있는 소스가 하나도 없음 (장애 상태). 일부 소스만 ACTIVE run이 없으면 그 소스를 `sources`에서 빼고 200으로 응답 |
| `AI_UNAVAILABLE` | 503 | 캐시가 없는 상태에서 ai-server 내부 소스 조회(6.3)가 실패함. 캐시가 있으면 만료됐어도 기존 캐시로 200 응답 |

**프론트 계약**

- 앱 시작 시 이 API 1회 호출 → `sources`로 버전 선택 드롭다운 구성, `comparePairs[0].compareEnabled`로 비교 탭 활성화/비활성화 결정.
- 하드코딩 버전 목록 사용 금지 (UI-01).
- 게스트 남은 횟수 표시는 `guest`로 초기화한다. 질문을 보낸 뒤에는 화면에서 1씩 줄이고, `GUEST_QUOTA_EXCEEDED`를 받으면 0으로 맞춘다.
- `sources`·`comparePairs`는 60초 캐시 값이고 `guest`는 요청마다 계산한다.

## 3. 채팅 (Chat)

> **서비스**: backend (Spring Boot) → ai-server (FastAPI) SSE 중계\
**대응 테이블**: `app.conversations`, `app.messages`, `app.message_sources`, `app.guest_sessions`\
**Rate Limit**: nginx `/api/v1/chat/**` 30 req/분 + backend 계층 이용량 한도

---

### 3.1 질문 스트리밍

- **Method / URI**: `POST /api/v1/chat/stream`
- **서비스**: backend (Spring Boot) — ai-server로 SSE 중계
- **인증**: JWT (로그인 사용자) 또는 게스트 쿠키 (`devdocs_sid`)
- **Rate Limit**: nginx 30 req/분 + backend 분당 10질문 / 일일 100질문 (COMPARE=2차감)
- **Idempotency**: 비멱등
- **설명**: 질문을 받아 SSE 스트림(`meta → token... → done`)으로 RAG 답변 반환. `conversationId` 없으면 대화 신규 생성 후 `meta` 이벤트로 ID 반환. 게스트는 SINGLE 모드만 허용.

**요청 바디**

```json
{
  "conversationId": null,
  "question":       "LangChain v0.3에서 Agent를 어떻게 생성하나요?",
  "mode":           "SINGLE",
  "sourceKey":      "langchain_v03",
  "sourceKeyA":     null,
  "sourceKeyB":     null,
  "history":        []
}
```

| 필드 | 타입 | 조건 | 설명 |
| --- | --- | --- | --- |
| `conversationId` | number \| null | 선택 | null이면 대화 신규 생성. 기존 대화에 이어서 질문 시 id 지정. |
| `question` | string | 필수, 1\~1000자 | 질문 원문 |
| `mode` | string | 필수 | `SINGLE` \| `COMPARE` |
| `sourceKey` | string \| null | SINGLE 필수 | 예: `"langchain_v03"` |
| `sourceKeyA` | string \| null | COMPARE 필수 | 구버전 source\_key |
| `sourceKeyB` | string \| null | COMPARE 필수 | 신버전 source\_key |
| `history` | array \| null | 선택 (게스트만) | 같은 화면의 최근 대화. `[{ "role": "user" \| "assistant", "content": string }]`, 오래된 것부터. 아래 규칙 참고 |

**`history` 규칙 (정책서 §5.1)**

- 게스트만 보낸다. 로그인 사용자가 보내면 무시하고 서버 DB 이력을 쓴다(조작된 맥락 주입 차단).
- 서버가 재검증·절단한다: 최근 6개(3턴)만 남기고 그보다 오래된 항목은 버린다. 메시지당 2,000자를 넘으면 앞 2,000자로 자른다.
- `role`이 `user`·`assistant`가 아니거나 `content`가 문자열이 아니면 `INVALID_REQUEST`(400, `field: "history"`)다.
- 절단 후 값을 ai-server 6.1 `history`로 그대로 넘긴다.
- 게스트 화면은 최근 3턴을 오래된 것부터 보낸다. 실패한 답변과 근거 부족(`NO_CONTEXT`) 답변은 빼고 그 턴의 질문은 남긴다(정책서 §5.2 제외 메시지).
- 로그인 사용자의 이력은 backend가 같은 대화의 최근 6개 메시지(3턴)를 DB에서 읽어 같은 규칙으로 만든다. 첫 질문(새 대화)은 빈 배열이다.
- 비교 대화의 이전 답변(`COMPLETED`)은 `compareResult`의 `version_a.summary`·`version_b.summary` 중 비어 있지 않은 것을 줄바꿈으로 이어 `assistant` 내용으로 쓴다(정책서 §5.6 멀티턴).
- backend는 보낸 이력과 `meta.rewrittenQuery`로 답변의 `rewrite_status`를 저장한다: 이력이 비었으면 `SKIPPED`, 재작성 질의가 있으면 `OK`, 이력을 보냈는데 null이면 `FALLBACK`.

**비교 모드 예시**

```json
{
  "conversationId": null,
  "question":       "Agent 생성 방식이 v0.3 대비 v1.x에서 어떻게 바뀌었나요?",
  "mode":           "COMPARE",
  "sourceKey":      null,
  "sourceKeyA":     "langchain_v03",
  "sourceKeyB":     "langchain_v1x"
}
```

**응답**: `200 OK`, `Content-Type: text/event-stream; charset=UTF-8`

스트림 전 검증 실패 시 일반 JSON 에러 반환. 스트림 시작 후 오류는 `event: error` SSE 이벤트로 전달.

```
data: {"event":"meta", "requestId":"uuid", "conversationId":42, "messageId":305, ...}

data: {"event":"token", "t":"LangChain v0.3에서 "}

data: {"event":"token", "t":"Agent를 생성하려면 "}

data: {"event":"done", "status":"COMPLETED", ...}
```

**SSE 이벤트 상세 — meta**

```json
{
  "event":          "meta",
  "requestId":      "a1b2c3d4-...",
  "conversationId": 42,
  "messageId":      305,
  "sourceKey":      "langchain_v03",
  "ingestRunId":    7,
  "commitSha":      "<COMMIT_SHA>",
  "ingestedAt":     "2026-10-05",
  "rewrittenQuery": "LangChain v0.3 Agent 생성 방법",
  "noContext":       false,
  "sources": [
    {
      "rank":        1,
      "headingPath": "Agents > Creating agents > Basic agent",
      "permalink":   "https://github.com/langchain-ai/langchain/blob/<COMMIT_SHA>/docs/agents.md?plain=1#L42-L89",
      "siteUrl":     "https://python.langchain.com/v0.3/docs/agents/",
      "similarity":  0.8732
    }
  ]
}
```

**SSE 이벤트 상세 — token**

```json
{ "event": "token", "t": "텍스트 조각" }
```

**SSE 이벤트 상세 — done**

```json
{
  "event":           "done",
  "status":          "COMPLETED",
  "statusReason":    null,
  "finishReason":    "stop",
  "usage":           { "prompt": 1240, "completion": 312 },
  "latency":         { "rewriteMs": 450, "embedMs": 80, "retrieveMs": 120, "ttftMs": 1850, "totalMs": 5300 },
  "invalidCitations": []
}
```

| done.status | 의미 |
| --- | --- |
| `COMPLETED` | 정상 완료 |
| `PARTIAL` | 토큰 1개 이상 수신 후 중단 |
| `NO_CONTEXT` | 유사도 < τ (LLM 미호출) 또는 LLM sentinel 감지 |
| `FAILED` | 오류·타임아웃 |

**SSE 이벤트 상세 — error** (스트림 시작 후 오류)

```json
{
  "event":     "error",
  "code":      "LLM_ERROR",
  "message":   "LLM 오류가 발생했습니다. 다시 질문해주세요.",
  "requestId": "a1b2c3d4-...",
  "partial":   true
}
```

**하트비트**: `: ping` 주석 10초 간격 전송. 클라이언트는 무시.

**스트림 전 에러 (일반 JSON 응답)**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | 필드 검증 실패 |
| `AUTH_TOKEN_MISSING` | 401 | 비로그인 + 쿠키 없음 |
| `AUTH_TOKEN_EXPIRED` | 401 | Access Token 만료 |
| `GUEST_MODE_NOT_ALLOWED` | 403 | 게스트 COMPARE 시도 |
| `CONVERSATION_NOT_FOUND` | 404 | 없는 대화 또는 타인 대화 |
| `SOURCE_NOT_FOUND` | 404 | source\_key 미존재 |
| `CONVERSATION_BUSY` | 409 | 진행 중 메시지 존재 |
| `CONVERSATION_FULL` | 409 | 메시지 100개 도달 |
| `SOURCE_UNAVAILABLE` | 409 | 비활성 버전 |
| `RATE_LIMITED` | 429 | 분당 10회 초과. `Retry-After` 포함 |
| `DAILY_QUOTA_EXCEEDED` | 429 | 일일 100회 초과 |
| `GUEST_QUOTA_EXCEEDED` | 429 | 게스트 5회 소진 |
| `GUEST_SESSION_LIMIT` | 429 | IP당 신규 세션 초과 |
| `CONCURRENT_STREAM_LIMIT` | 429 | 동시 스트림 초과 |
| `INDEX_NOT_ACTIVE` | 503 | ACTIVE run 없음 |
| `AI_UNAVAILABLE` | 503 | ai-server 연결 3초 실패, 또는 ai-server 스트림 전 오류 중 아래 그대로 전달하는 코드가 아닌 것(`INTERNAL_UNAUTHORIZED`·`INTERNAL_ERROR`·`INVALID_REQUEST` 등) |
| `AI_BUSY` | 503 | ai-server 동시 생성 한도 초과 (ai-server 응답 그대로 전달) |
| `EMBEDDING_MODEL_MISMATCH` | 500 | ai-server 응답 그대로 전달 |

- backend는 ai-server 응답 헤더(HTTP 상태)를 받을 때까지 기다린 뒤 브라우저에 200을 보낸다. ai-server가 스트림 전 오류(6.1 표)를 주면 브라우저도 일반 JSON 오류를 받는다. 그대로 전달하는 코드: `SOURCE_NOT_FOUND`·`SOURCE_UNAVAILABLE`·`INDEX_NOT_ACTIVE`·`AI_BUSY`·`EMBEDDING_MODEL_MISMATCH`.
- 기존 대화(`conversationId` 지정)의 버전 값이 대화 설정과 다르면 `INVALID_REQUEST`(400), 메시지 100개면 `CONVERSATION_FULL`, 대화의 소스가 비활성이면 `SOURCE_UNAVAILABLE`이다(정책서 §5.1·§2.3). 버전 값을 생략하면 대화 설정을 쓴다.
**비교 모드 (`COMPARE`) 규칙** (정책서 §3.2·§5.6·§8.1, ADR-010)

- 로그인 사용자만 쓴다. 게스트는 `GUEST_MODE_NOT_ALLOWED`(403)이다.
- 새 대화는 `sourceKeyA`·`sourceKeyB`가 필요하다. 없으면 `INVALID_REQUEST`(해당 필드), 같으면 `INVALID_REQUEST`(`sourceKeyB`)다.
- 두 소스는 메타 API `comparePairs`에 같은 순서(A = 구버전, B = 신버전)로 있어야 한다. 아니면 `INVALID_REQUEST`(`sourceKeyB`)다. 두 소스 각각에 `sourceKey`와 같은 검사(`SOURCE_NOT_FOUND`·`SOURCE_UNAVAILABLE`·`INDEX_NOT_ACTIVE`)를 한다.
- 이어서 질문은 `conversationId`만으로 충분하다. `mode`가 대화와 다르면 `INVALID_REQUEST`(`mode`), 함께 온 버전 값이 대화와 다르면 `INVALID_REQUEST`(해당 필드)다. 단일 모드 요청의 `sourceKeyA/B`, 비교 모드 요청의 `sourceKey`는 null이어야 한다.
- 일일 한도는 2회로 차감한다(USER 메시지 `quota_cost` = 2). 분당 한도는 1회, 동시 스트림 자리는 1개를 쓴다.
- 브라우저 이벤트는 `meta`(부록 B.4, `conversationId`·`messageId` 추가) → `done`(`compareResult`) 또는 `error`다. token은 없다.
- 저장: 요청 수락 시 ASSISTANT `PENDING` → ai-server가 200을 주면 `PROCESSING` → `meta`에서 A·B 스냅샷(`ingest_run_id_a/b`·`commit_sha_a/b`·`ingested_at_a/b`·`top1_similarity_a/b`)과 출처(`rank_label` A1…·B1…, 측별 `source_key`) 저장 → 종결 시 `compare_result`(후처리 결과 그대로)와 사용량·지연을 한 번에 저장한다. `content`는 NULL이다.
- 브라우저가 중간에 나가도 업스트림 취소를 전파하지 않고 끝까지 처리해 저장한다(정책서 §2.3). 동시 스트림 자리는 처리가 끝날 때 반납한다.
- 비교 모드 오류 종결: ai-server `error`(`COMPARE_PARSE_ERROR`·`UPSTREAM_TIMEOUT`·`LLM_ERROR` 등)는 그 코드로 `FAILED`, 첫 이벤트 15초·유휴 30초 초과는 `UPSTREAM_TIMEOUT`이다(아래 표). 비교 모드는 토큰이 없으므로 `PARTIAL`이 없다.

**스트림 후 `error` 이벤트 (backend가 보내는 코드)**

| 상황 | `code` | `partial` | 저장 상태(`status_reason`) |
| --- | --- | --- | --- |
| ai-server `error` 이벤트 | ai-server 코드 그대로. 단 `INTERNAL_ERROR`·`INTERNAL_UNAUTHORIZED`는 `AI_UNAVAILABLE` | 브라우저에 보낸 토큰 ≥ 1 | 토큰 ≥ 1: PARTIAL, 0: FAILED (ai-server 코드) |
| 첫 이벤트 15초 초과 | `UPSTREAM_TIMEOUT` | false | FAILED (`UPSTREAM_TIMEOUT`) |
| 이벤트 간격 30초 초과 | `UPSTREAM_TIMEOUT` | 토큰 ≥ 1 | PARTIAL·FAILED (`UPSTREAM_IDLE_TIMEOUT`) |
| ai-server 연결이 종결 이벤트 없이 끊김 | `AI_UNAVAILABLE` | 토큰 ≥ 1 | PARTIAL·FAILED (`AI_UNAVAILABLE`) |

**처리 흐름 (backend)**

1. 입력 검증 → INV-11 검사 (SELECT ... FOR UPDATE) → 이용량 차감
2. `app.messages`에 USER INSERT + ASSISTANT PENDING INSERT (동일 트랜잭션)
3. WebClient로 ai-server `/internal/v1/chat/stream` SSE 호출 (스트리밍 중계)
4. `meta` 수신 → ASSISTANT STREAMING 갱신 + message\_sources INSERT
5. token 수신 → 메모리 버퍼 누적 (DB 미기록)
6. `done` / `error` / 클라이언트 취소 → 최종 UPDATE 1회
7. 게스트: 2·4·6 DB 미기록, `guest_usage_log`만 기록

**프론트 계약**

- SSE는 `fetch` + `ReadableStream` 파싱 (`EventSource` 미사용 — Authorization 헤더 불가).
- `meta` 수신 즉시 출처 카드 표시 (UI-02).
- 스트림 실패(error 이벤트·네트워크 오류) 시 재연결하지 않고 재질문 버튼 표시.
- 게스트 `devdocs_sid` 쿠키는 최초 질문 API 호출 시 서버가 발급 (페이지 진입만으로는 미발급).

## 4. 대화 (Conversations)

> **서비스**: backend (Spring Boot)\
**대응 테이블**: `app.conversations`, `app.messages`, `app.message_sources`\
**인증**: JWT 필수 (게스트 접근 불가, 대화 영구 보존)

---

### 4.1 대화 목록 조회

- **Method / URI**: `GET /api/v1/conversations`
- **인증**: JWT
- **Idempotency**: 멱등
- **설명**: 본인 대화 목록. `updated_at` 내림차순. 커서 기반 페이지네이션 20개. 삭제 API 없음(영구 보존).

**쿼리 파라미터**

| 파라미터 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `before` | string | — | ISO 8601 커서. 이 시각보다 이전 `updated_at`인 대화만 반환 |
| `size` | int | 20 | 최대 20 |

**응답 200**

```json
{
  "success": true,
  "message": null,
  "data": {
    "items": [
      {
        "conversationId": 42,
        "title":          "LangChain v0.3에서 Agent를 어떻",
        "mode":           "SINGLE",
        "sourceKey":      "langchain_v03",
        "sourceKeyA":     null,
        "sourceKeyB":     null,
        "versionLabel":   "v0.3",
        "messageCount":   6,
        "lastMessageStatus": "COMPLETED",
        "status":         "OPEN",
        "updatedAt":      "2026-10-01T09:30:00Z"
      }
    ],
    "cursor":  "2026-10-01T09:30:00Z",
    "hasNext": true
  }
}
```

| 필드 | 설명 |
| --- | --- |
| `title` | 첫 USER 메시지 앞 40자 (줄바꿈 제거) |
| `versionLabel` | SINGLE: `sources.version_label`. COMPARE: `"v0.3 vs v1.x"` 형식 |
| `status` | `OPEN` (질문 가능) / `READ_ONLY` (100개 도달 또는 소스 비활성) — 파생값 |
| `lastMessageStatus` | 최신 ASSISTANT 메시지 status. null이면 USER 메시지만 존재 |
| `cursor` | 다음 페이지 `before` 파라미터 값. 마지막 페이지이면 null |

**조회 규칙**

- 정렬은 `updatedAt` 내림차순, 같은 시각이면 `conversationId` 내림차순이다. `cursor`는 이번 페이지 마지막 항목의 `updatedAt`이다.
- `versionLabel`·`status`는 소스 카탈로그(§6.3, 60초 캐시)로 계산한다. 카탈로그에 없는 `sourceKey`는 비활성으로 보고, `versionLabel`에는 `sourceKey` 값을 그대로 쓴다.
- 카탈로그를 가져올 수 없으면(ai-server 장애, 캐시 없음) 목록 조회를 실패시키지 않는다. `status`는 메시지 수로만 판정하고 `versionLabel`은 `sourceKey` 값을 쓴다. 이어서 질문은 질문 시점에 다시 검증한다(§3.1).

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | `size`가 1~20 밖이거나 `before`가 ISO 8601 시각이 아님 |
| `AUTH_TOKEN_MISSING` | 401 | JWT 없음 |
| `AUTH_TOKEN_EXPIRED` | 401 | Access Token 만료 |

---

### 4.2 대화 상세 조회

- **Method / URI**: `GET /api/v1/conversations/{conversationId}`
- **인증**: JWT
- **Idempotency**: 멱등
- **설명**: 대화 + 전체 메시지(시간순) + 출처 반환. 소유자만 접근 가능 (INV-14). 타인·미존재 대화는 404로 통일.

**경로 변수**: `conversationId` — 정수

**응답 200**

```json
{
  "success": true,
  "message": null,
  "data": {
    "conversationId": 42,
    "title":          "LangChain v0.3에서 Agent를 어떻",
    "mode":           "SINGLE",
    "sourceKey":      "langchain_v03",
    "sourceKeyA":     null,
    "sourceKeyB":     null,
    "status":         "OPEN",
    "messageCount":   6,
    "createdAt":      "2026-10-01T09:00:00Z",
    "updatedAt":      "2026-10-01T09:30:00Z",
    "messages": [
      {
        "messageId":  301,
        "role":       "USER",
        "content":    "LangChain v0.3에서 Agent를 어떻게 생성하나요?",
        "createdAt":  "2026-10-01T09:00:10Z"
      },
      {
        "messageId":    302,
        "role":         "ASSISTANT",
        "content":      "LangChain v0.3 (<COMMIT_SHA> · 2026-10-05 수집)\n\n...[1] ...",
        "status":       "COMPLETED",
        "statusReason": null,
        "requestId":    "a1b2c3d4-...",
        "rewrittenQuery": null,
        "snapshot": {
          "versionLabel": "v0.3",
          "commitSha":    "<COMMIT_SHA>",
          "ingestedAt":   "2026-10-05"
        },
        "usage":   { "prompt": 1240, "completion": 312 },
        "latency": { "rewriteMs": 0, "embedMs": 80, "retrieveMs": 120, "ttftMs": 1850, "totalMs": 5300 },
        "sources": [
          {
            "rank":        1,
            "rankLabel":   "1",
            "headingPath": "Agents > Creating agents > Basic agent",
            "permalink":   "https://github.com/langchain-ai/langchain/blob/<COMMIT_SHA>/agents.md?plain=1#L42-L89",
            "siteUrl":     "https://python.langchain.com/v0.3/docs/agents/",
            "similarity":  0.8732
          }
        ],
        "createdAt":  "2026-10-01T09:00:10Z",
        "updatedAt":  "2026-10-01T09:00:15Z"
      }
    ]
  }
}
```

**응답 규칙**

- `messages`는 생성 시각 오름차순, 같은 시각이면 `messageId` 오름차순이다. `status`·`messageCount`는 §4.1과 같은 규칙으로 계산한다.
- 종결 전(`PENDING`·`STREAMING`·`PROCESSING`) ASSISTANT의 `content`는 빈 문자열이다. 토큰은 종결 시 한 번만 저장한다(정책서 §6.3).
- `snapshot`은 `meta`를 받기 전에 끝난 답변(수집 커밋 SHA 없음)이면 null이다. `snapshot.versionLabel`은 §4.1 `versionLabel`과 같은 규칙으로 정한다.
- `usage`는 토큰 수가 없으면 null이다. `latency`는 다섯 값이 모두 없으면 null이고, 일부만 없으면 그 값만 null이다.
- `sources[].rank`는 `rankLabel`의 순번 숫자다. 출처가 없으면 빈 배열이다.
- `rewrittenQuery`는 재작성하지 않았거나(첫 질문·`SKIPPED`) 폴백한 경우 null이다.

**비교 모드 ASSISTANT 메시지 추가 필드** (`mode = COMPARE`)

```json
{
  "compareResult": {
    "version_a": { "summary": "...", "citations": ["A1", "A3"], "no_evidence": false },
    "version_b": { "summary": "...", "citations": ["B2"],         "no_evidence": false },
    "changes": [
      {
        "aspect":      "에이전트 생성 함수",
        "a":           "AgentExecutor.from_agent_and_tools(...)",
        "b":           "create_react_agent(...)",
        "citations_a": ["A1"],
        "citations_b":  ["B2"]
      }
    ]
  },
  "snapshot": {
    "commitShaA": "<COMMIT_SHA_A>",
    "ingestedAtA": "2026-10-05",
    "commitShaB": "<COMMIT_SHA_B>",
    "ingestedAtB": "2026-10-05"
  }
}
```

- `content`는 빈 문자열이다(비교 답변은 본문 없이 `compareResult`만 저장).
- `compareResult`는 `COMPLETED`일 때만 값이 있고, 그 밖에는 null이다. 내부 키는 snake_case 그대로다(정책서 §9.3).
- `snapshot`은 위 네 필드다. `meta`를 받기 전에 끝난 답변이면 null이다. `ingestedAtA/B`는 그 측 값이 없으면 null이다.
- `sources[].rankLabel`은 `A1…`·`B1…`이고, `rank`는 그 순번 숫자다.

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | `conversationId`가 정수가 아님 |
| `AUTH_TOKEN_MISSING` | 401 | JWT 없음 |
| `AUTH_TOKEN_EXPIRED` | 401 | Access Token 만료 |
| `CONVERSATION_NOT_FOUND` | 404 | 없는 대화 또는 타인 대화 (INV-14) |

## 5. 관리자 (Admin)

> **서비스**: backend (Spring Boot)\
**인증**: JWT + `ROLE_ADMIN` 필수. 비관리자 → `FORBIDDEN`(403)\
**데이터 출처**: 인덱스 정보는 ai-server 내부 API 경유(backend는 ai 스키마 테이블을 직접 읽지 않음, §6.6), 사용량은 `app.messages`·`app.guest_usage_logs` 집계

---

### 5.1 인덱스 현황 대시보드

- **Method / URI**: `GET /api/v1/admin/index/status`
- **인증**: JWT + ADMIN
- **Idempotency**: 멱등
- **설명**: 소스별 ACTIVE 인덱스 정보 + 최근 수집 이력 + 일별 토큰 사용량 집계. ADM-01 요구사항.

**응답 200**

```json
{
  "success": true,
  "message": null,
  "data": {
    "sources": [
      {
        "sourceKey":      "langchain_v03",
        "displayName":    "LangChain v0.3",
        "enabled":        true,
        "activeRun": {
          "ingestRunId":     7,
          "status":          "ACTIVE",
          "commitSha":       "<COMMIT_SHA>",
          "chunkStrategy":   "B",
          "chunkCount":      3842,
          "prevChunkCount":  3790,
          "embeddingModel":  "text-embedding-3-small",
          "embeddingTokens": 2150000,
          "embeddingCostUsd": 0.042,
          "ingestDurationMs": 48500,
          "startedAt":       "2026-10-05T02:00:00Z",
          "completedAt":     "2026-10-05T02:00:48Z"
        },
        "recentRuns": [
          {
            "ingestRunId": 7, "status": "ACTIVE",    "startedAt": "2026-10-05T02:00:00Z" },
          { "ingestRunId": 5, "status": "SUPERSEDED", "startedAt": "2026-09-28T02:00:00Z" },
          { "ingestRunId": 3, "status": "FAILED",     "startedAt": "2026-09-21T02:00:00Z", "failureStage": "VALIDATING" }
        ]
      }
    ],
    "usageSummary": {
      "today": {
        "date":             "2026-10-01",
        "totalMessages":    148,
        "promptTokens":     183400,
        "completionTokens": 44200,
        "guestSessions":    32
      },
      "last7Days": [
        { "date": "2026-09-25", "totalMessages": 95, "promptTokens": 118000, "completionTokens": 28500 }
      ]
    }
  }
}
```

**응답 규칙**

- `sources`는 ai-server §6.6 응답을 그대로 옮긴다. 카탈로그의 모든 소스(비활성 포함)이고, `activeRun`은 ACTIVE run이 없으면 null이다.
- `recentRuns`는 소스별 최근 수집 run 5개(`created_at` 내림차순)다. `failureStage`는 `FAILED`일 때만 있고, `startedAt`은 수집을 시작하지 않은 run이면 null이다.
- `usageSummary`의 날짜는 KST(정책서 §8.1 일일 한도와 같은 기준)다.
  - `totalMessages`: 그날 질문 수 = 회원 USER 메시지 수 + 게스트 이용 기록(`guest_usage_logs`) 수
  - `promptTokens`·`completionTokens`: 그날 생성된 회원 ASSISTANT 메시지와 게스트 이용 기록의 토큰 합(없으면 0)
  - `today.guestSessions`: 오늘 이용 기록이 있는 게스트 세션 수(서로 다른 `sid_hash`)
  - `last7Days`: 오늘을 포함한 최근 7일, 오래된 날부터. 기록이 없는 날도 0으로 넣는다. `guestSessions`는 없다(세션 행은 만료 후 삭제돼 과거 날짜를 셀 수 없음)
- 금액·토큰 단위: `embeddingCostUsd`는 달러(소수), 시각은 UTC ISO-8601이다.

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `AUTH_TOKEN_MISSING` | 401 | JWT 없음 |
| `FORBIDDEN` | 403 | ROLE\_USER 접근 |
| `AI_UNAVAILABLE` | 503 | ai-server 인덱스 현황(§6.6) 호출 실패 |

---

### 5.2 재수집 트리거 (P2)

- **Method / URI**: `POST /api/v1/admin/index/ingest/{sourceKey}`
- **인증**: JWT + ADMIN
- **Rate Limit**: 없음 (운영 환경 자체 403)
- **Idempotency**: 비멱등
- **설명**: 지정 소스의 수집·임베딩·검증·활성화를 백그라운드로 실행. local·staging 프로필 전용. prod 환경 호출 시 `FORBIDDEN_IN_PROFILE`(403).

**경로 변수**: `sourceKey` — 문자열 예: `langchain_v03`

**요청 바디** (선택)

```json
{
  "acceptDrift": false
}
```

| 필드 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `acceptDrift` | boolean | false | VALIDATING 게이트에서 청크 수 드리프트(직전 ACTIVE 대비 ±30% 초과, `policy.md` §4.4) 허용 시 true |

**응답 202**

```json
{
  "success": true,
  "message": "수집이 시작되었습니다. 인덱스 현황 API에서 진행 상태를 확인하세요.",
  "data": { "ingestRunId": 9 }
}
```

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `AUTH_TOKEN_MISSING` | 401 | JWT 없음 |
| `FORBIDDEN` | 403 | ROLE\_USER 접근 |
| `FORBIDDEN_IN_PROFILE` | 403 | prod 환경 호출 |
| `SOURCE_NOT_FOUND` | 404 | sourceKey 미존재 |

---

### 5.3 사용자 목록

- **Method / URI**: `GET /api/v1/admin/users`
- **인증**: JWT + ADMIN
- **Idempotency**: 멱등
- **설명**: 가입 사용자 목록과 이용량. 게스트는 계정이 아니므로 넣지 않는다(게스트 이용은 §5.1 사용량과 §5.5 요청 로그). 비밀번호 해시·토큰 정보는 내보내지 않는다.

**쿼리 파라미터**

| 파라미터 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `query` | string | — | 이메일 부분 일치(대소문자 무시, 앞뒤 공백 제거, 최대 254자) |
| `before` | string | — | ISO 8601 커서. 이 시각보다 이전에 가입한 사용자만 반환 |
| `size` | int | 20 | 1~50 |

**응답 200**

```json
{
  "success": true,
  "message": null,
  "data": {
    "items": [
      {
        "userId":         12,
        "email":          "user1@example.com",
        "role":           "ROLE_USER",
        "status":         "LOCKED",
        "lockedUntil":    "2026-11-18T03:15:00Z",
        "createdAt":      "2026-10-15T09:00:00Z",
        "totalQuestions": 142,
        "todayQuotaUsed": 7,
        "dailyQuota":     100
      }
    ],
    "cursor":  "2026-10-15T09:00:00Z",
    "hasNext": false,
    "summary": { "totalUsers": 6, "admins": 1, "members": 5, "locked": 1 }
  }
}
```

| 필드 | 설명 |
| --- | --- |
| `status` | `LOCKED`는 잠금 후 15분이 지나지 않은 계정이다(정책서 §1.2, 조회 시 판정). 그 밖은 `ACTIVE` |
| `lockedUntil` | 잠금이 풀리는 시각. `ACTIVE`이면 null |
| `totalQuestions` | 지금까지의 질문 수(USER 메시지 수) |
| `todayQuotaUsed` · `dailyQuota` | 오늘(KST) 사용한 일일 한도(`quota_cost` 합, 비교 = 2)와 일일 한도(관리자 포함 같은 값, 정책서 §8.1) |
| `cursor` | 이번 페이지 마지막 항목의 `createdAt`. 마지막 페이지이면 null |
| `summary` | 검색과 무관한 전체 계정 수: 전체·관리자(`ROLE_ADMIN`)·일반(`ROLE_USER`)·잠김(`status = LOCKED`) |

- 정렬은 `createdAt` 내림차순, 같은 시각이면 `userId` 내림차순이다.

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | `size`가 1~50 밖, `before`가 ISO 8601이 아님, `query`가 254자 초과 |
| `AUTH_TOKEN_MISSING` | 401 | JWT 없음 |
| `FORBIDDEN` | 403 | ROLE\_USER 접근 |

---

### 5.4 계정 잠금 해제

- **Method / URI**: `POST /api/v1/admin/users/{userId}/unlock`
- **인증**: JWT + ADMIN
- **Idempotency**: 멱등 (잠기지 않은 계정도 같은 결과)
- **설명**: 로그인 실패 잠금을 즉시 푼다. 실패 횟수·실패 구간 시작 시각·잠금 시각을 지우고 `ACTIVE`로 바꾼다(정책서 §10.3). 다른 계정 정보는 바꾸지 않는다.

**응답 200**: §5.3 `items[]`와 같은 형식의 사용자 1명

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | `userId`가 정수가 아님 |
| `AUTH_TOKEN_MISSING` | 401 | JWT 없음 |
| `FORBIDDEN` | 403 | ROLE\_USER 접근 |
| `USER_NOT_FOUND` | 404 | 없는 사용자 |

---

### 5.5 요청 로그

- **Method / URI**: `GET /api/v1/admin/logs`
- **인증**: JWT + ADMIN
- **Idempotency**: 멱등
- **설명**: 최근 요청의 결과를 시각 내림차순으로 보여 준다. 별도 로그 저장소 없이 DB 기록을 쓴다: 회원 답변(종결된 ASSISTANT 메시지) + 게스트 이용 기록(`guest_usage_logs`). 질문 원문·이메일은 넣지 않는다(정책서 §9.4).

**쿼리 파라미터**

| 파라미터 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `level` | string | — | `INFO` \| `WARN` \| `ERROR`. 없으면 전체 |
| `before` | string | — | ISO 8601 커서. 이 시각보다 이전 항목만 반환 |
| `size` | int | 20 | 1~50 |

**응답 200**

```json
{
  "success": true,
  "message": null,
  "data": {
    "items": [
      {
        "at":           "2026-11-18T09:02:15Z",
        "level":        "ERROR",
        "actor":        "USER",
        "userId":       12,
        "requestId":    "c04e5f72-...",
        "mode":         "SINGLE",
        "status":       "FAILED",
        "statusReason": "LLM_ERROR",
        "totalMs":      4120,
        "promptTokens":     null,
        "completionTokens": null
      },
      {
        "at":           "2026-11-18T09:01:40Z",
        "level":        "INFO",
        "actor":        "GUEST",
        "userId":       null,
        "requestId":    null,
        "mode":         "SINGLE",
        "status":       "COMPLETED",
        "statusReason": null,
        "totalMs":      null,
        "promptTokens":     1240,
        "completionTokens": 312
      }
    ],
    "cursor":  "2026-11-18T09:01:40Z",
    "hasNext": true
  }
}
```

| 필드 | 설명 |
| --- | --- |
| `at` | 회원: 답변이 종결된 시각(`messages.updated_at`). 게스트: 기록 시각 |
| `level` | `FAILED` → `ERROR`, `PARTIAL`·`NO_CONTEXT` → `WARN`, `COMPLETED` → `INFO` |
| `actor` · `userId` | `USER`(회원 ID) 또는 `GUEST`(null) |
| `requestId` · `statusReason` · `totalMs` | 회원 답변의 값. 게스트 기록에는 없어 null |
| `mode` | 회원: 대화 모드(`SINGLE`·`COMPARE`). 게스트: `SINGLE` |
| `cursor` | 이번 페이지 마지막 항목의 `at`. 마지막 페이지이면 null |

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | `level`이 세 값이 아님, `size`가 1~50 밖, `before`가 ISO 8601이 아님 |
| `AUTH_TOKEN_MISSING` | 401 | JWT 없음 |
| `FORBIDDEN` | 403 | ROLE\_USER 접근 |

---

## 6. 내부 API (ai-server · FastAPI)

> **서비스**: ai-server (Python FastAPI + uvicorn)\
**Base URL**: `http://ai-server:8000` (Docker Compose 내부망 전용)\
**노출 범위**: 외부 인터넷 미노출. nginx에서 `/internal/**` 차단\
**인증**: `X-Internal-Token` 헤더 = `INTERNAL_TOKEN` (ADR-012). 누락·불일치 시 401 `INTERNAL_UNAUTHORIZED`. 토큰이 설정되지 않은 서버는 모든 요청을 거부한다. 예외: `GET /internal/v1/health`(Compose healthcheck)\
**FastAPI 문서**: `/docs` — local·staging 프로필만 노출 (prod 비노출, 9.1 참고)

---

### 6.1 스트리밍 질의

- **Method / URI**: `POST /internal/v1/chat/stream`
- **서비스**: ai-server (FastAPI)
- **인증**: `X-Internal-Token`
- **설명**: backend의 WebClient가 호출. 검색·재작성·생성을 수행하고 SSE 이벤트 스트림 반환. asyncio Semaphore 20으로 동시 생성 제한.

**요청 바디**

```json
{
  "requestId":      "a1b2c3d4-...",
  "mode":           "SINGLE",
  "sourceKey":      "langchain_v03",
  "sourceKeyA":     null,
  "sourceKeyB":     null,
  "question":       "Agent를 어떻게 생성하나요?",
  "history": [
    { "role": "user",      "content": "LangChain에서 Tool이 뭔가요?" },
    { "role": "assistant", "content": "Tool은 Agent가 호출할 수 있는 함수입니다..." }
  ],
  "promptVersion": "single_v3"
}
```

| 필드 | 설명 |
| --- | --- |
| `requestId` | 선택. 없으면 `X-Request-Id` 헤더, 그것도 없으면 ai-server가 UUID v4 생성 |
| `mode` | `SINGLE` \| `COMPARE` |
| `sourceKey` | `SINGLE`이면 필수 |
| `sourceKeyA`·`sourceKeyB` | `COMPARE`이면 둘 다 필수. `ai.compare_pairs`에 같은 순서(A = 구버전, B = 신버전)로 있는 쌍만 허용하고, 아니면 400 `INVALID_REQUEST`(정책서 §3.2). 두 소스 각각에 `sourceKey`와 같은 스트림 전 검사(404·409·500·503)를 적용한다 |
| `question` | trim 후 1~1,000자 (정책서 §5.1) |
| `history` | 최근 3턴, 오래된 것부터. 첫 질문이면 빈 배열 `[]`. 최대 6개, 메시지당 2,000자. 실패·근거 부족 답변은 보내는 쪽(backend)이 뺀다. 비어 있지 않으면 질의를 재작성한다(정책서 §5.2) — `assistant` 항목은 앞 500자만 쓴다. 재작성 성공이면 `meta.rewrittenQuery`에 재작성 질의, 빈 배열·폴백이면 null. `done.latency.rewriteMs`는 재작성을 시도했으면 걸린 시간, 빈 배열이면 null |
| `promptVersion` | 선택. `ai-server/configs/prompts/` 파일명(확장자 제외). backend가 환경 변수로 주입. 없으면 `ai-server/configs/rag.yaml`의 `generation.prompt_version`(SINGLE)·`generation.compare_prompt_version`(COMPARE). 없는 버전이면 400 |

**응답**: `200 OK`, `text/event-stream`

```
data: {"event":"meta", "requestId":"a1b2c3d4", "sourceKey":"langchain_v03", "ingestRunId":7, "commitSha":"<COMMIT_SHA>", "ingestedAt":"2026-10-05", "rewrittenQuery":"Agent 생성 방법", "noContext":false, "sources":[...]}

data: {"event":"token", "t":"LangChain v0.3에서 "}

data: {"event":"done", "status":"COMPLETED", "finishReason":"stop", "usage":{"prompt":1240,"completion":312}, "latency":{"rewriteMs":450,"embedMs":80,"retrieveMs":120,"ttftMs":1850,"totalMs":5300}, "invalidCitations":[], "model":"gpt-4o-mini-2024-07-18", "promptVersion":"single_v1"}
```

**NO\_CONTEXT 시 응답 (LLM 미호출)**

```
data: {"event":"meta", ..., "noContext":true, "sources":[]}

data: {"event":"done", "status":"NO_CONTEXT", "statusReason":"LOW_SIMILARITY", "finishReason":null, "usage":null, "latency":{...}}
```

**에러 (스트림 전)**

```json
{ "code": "AI_BUSY", "message": "시스템이 혼잡합니다.", "request_id": "a1b2c3d4", "timestamp": "2026-10-01T10:15:30Z" }
```

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | 필드 검증 실패 (Pydantic), 없는 `promptVersion`, 허용되지 않은 비교 쌍 |
| `INTERNAL_UNAUTHORIZED` | 401 | `X-Internal-Token` 누락·불일치 (ADR-012) |
| `SOURCE_NOT_FOUND` | 404 | `sourceKey`가 소스 카탈로그에 없음 |
| `SOURCE_UNAVAILABLE` | 409 | 비활성 소스 |
| `EMBEDDING_MODEL_MISMATCH` | 500 | 인덱스 임베딩 모델 ≠ 질의 임베딩 모델 (INV-03) |
| `INDEX_NOT_ACTIVE` | 503 | ACTIVE run 없음 또는 그 컬렉션 없음 (INV-01) |
| `AI_BUSY` | 503 | asyncio Semaphore 소진 |

**종결 상태 (스트림 후, 정책서 §10.2)**

| 조건 | 종결 이벤트 |
| --- | --- |
| `finishReason=stop` | `done` COMPLETED |
| `finishReason=length` | `done` PARTIAL, `statusReason=LENGTH` |
| 그 밖의 `finishReason`(예: `content_filter`) | `done` PARTIAL, `statusReason`=대문자 사유 |
| 유사도 미달 | `meta(noContext=true)` → `done` NO_CONTEXT, `LOW_SIMILARITY` |
| sentinel `[[NO_ANSWER]]` | `meta`(sources 포함) → `done` NO_CONTEXT, `LLM_ABSTAIN` (토큰 없음) |
| 단일 스트림 120초 초과 | 토큰 ≥ 1: `done` PARTIAL, 0개: `done` FAILED — 둘 다 `statusReason=MAX_DURATION` |
| 질의 임베딩·OpenAI 생성 실패 | `error` `LLM_ERROR` (`partial` = 토큰 수신 여부) |
| 스트림 중 인덱스 오류(컬렉션 삭제 등) | `error` + 해당 코드(`INDEX_NOT_ACTIVE` 등) |
| 그 밖의 예기치 않은 서버 오류 | `error` `INTERNAL_ERROR` (종결 이벤트 1회 보장, INV-06) |

**비교 모드 (`COMPARE`, 부록 B.2·B.4, 정책서 §5.6)**

- 재작성 질의 1개로 A·B를 각각 검색하고, 각 소스의 τ로 근거 여부를 따로 판정한다.
- `meta.sources`는 τ를 통과한 측의 컨텍스트 청크만 담는다. rank는 A측 `A1…`, B측 `B1…`이다. 근거가 없는 측의 출처는 넣지 않는다.
- `meta`에는 두 소스의 `sourceKeyA/B`·`ingestRunIdA/B`·`commitShaA/B`·`ingestedAtA/B`를 넣고 단일 모드 필드(`sourceKey` 등)는 넣지 않는다.
- token 이벤트를 보내지 않는다. 생성은 OpenAI Structured Outputs 1회 호출이며, 후처리한 결과를 `done.compareResult`로 보낸다.
- `done`: `finishReason`은 `stop`, `usage`는 생성 호출 합계(재시도 포함), `latency.ttftMs`는 null, `invalidCitations`는 후처리에서 지운 인용 번호(`"A9"` 등), `promptVersion`은 비교 프롬프트 버전이다.

| 조건 | 종결 이벤트 |
| --- | --- |
| 양쪽 top-1 < τ | `meta(noContext=true, sources=[])` → `done` NO_CONTEXT, `LOW_SIMILARITY` (생성 LLM 미호출) |
| 한쪽 top-1 < τ | `meta`(통과한 측 출처만) → `done` COMPLETED. 근거 없는 측은 `no_evidence=true`·`summary=""`·`citations=[]`, `changes=[]` |
| 정상 | `meta` → `done` COMPLETED, `compareResult` |
| 구조화 출력 파싱 실패(스키마 불일치·`finish_reason=length`·거절) 2회 | `error` `COMPARE_PARSE_ERROR` (`partial=false`) |
| OpenAI 호출 실패·질의 임베딩 실패 | `error` `LLM_ERROR` (`partial=false`, 재시도 없음) |
| 요청부터 30초 초과 (정책서 §2.1 비교 모드 전체 타임아웃) | `error` `UPSTREAM_TIMEOUT` (`partial=false`) |

**에러 (스트림 후)**: `event: error` SSE 이벤트

```json
{ "event": "error", "code": "LLM_ERROR", "message": "LLM 오류가 발생했습니다.", "requestId": "a1b2c3d4", "partial": false }
```

**처리 파이프라인 (ai-server 내부)**

1. 요청 검증 (Pydantic) + Semaphore 획득
2. 질의 재작성 — `history` 존재 시 LLM 호출, 첫 질문이면 SKIPPED
3. 임베딩 — `text-embedding-3-small`
4. 벡터 검색 — Chroma PersistentClient, top-K, cosine. INV-02 2차 메타데이터 검증
5. 유사도 < τ → NO\_CONTEXT (meta + done 즉시 반환, LLM 미호출)
6. 프롬프트 조립 + OpenAI 스트리밍 호출 (temperature 0, max\_tokens 1024)
7. ai-server가 응답 앞부분을 보류해 sentinel `[[NO_ANSWER]]` 판정 — 맨 앞 또는 기준 버전 머리말 바로 뒤의 sentinel이면 토큰 없이 NO\_CONTEXT 종결 (보류 최대 머리말 길이 + 16자, 정책서 §5.4)
8. token 이벤트 스트리밍 → done 이벤트
9. Semaphore 해제

---

### 6.2 헬스체크

- **Method / URI**: `GET /internal/v1/health`
- **서비스**: ai-server (FastAPI)
- **인증**: 없음 (내부망 전용, Compose healthcheck가 헤더 없이 호출)
- **설명**: Docker Compose `healthcheck`에서 호출. Chroma 로드 여부 + 소스별 ACTIVE run 존재 확인.

**응답 200 (정상)**

```json
{
  "status": "ok",
  "chroma": "loaded",
  "sources": {
    "langchain_v03": { "activeRun": true,  "ingestRunId": 7 },
    "langchain_v1x": { "activeRun": true,  "ingestRunId": 8 }
  }
}
```

**응답 503 (비정상)**

```json
{
  "status": "degraded",
  "chroma": "loaded",
  "sources": {
    "langchain_v03": { "activeRun": false, "ingestRunId": null }
  }
}
```

`langchain_v1x` 같이 ACTIVE run이 없는 소스가 있으면 503 반환. backend는 이 응답으로 `INDEX_NOT_ACTIVE` 사전 차단 가능.

- 판정 대상은 `ai.sources.enabled = true`인 소스다. 비활성 소스는 응답에 넣지 않는다.
- `activeRun = true`는 포인터가 ACTIVE run을 가리키고 그 Chroma 컬렉션(`{source_key}_run{id}`)이 있을 때만이다. 컬렉션이 없으면 질의가 `INDEX_NOT_ACTIVE`로 실패하므로 `false`다.
- `chroma`: Chroma 클라이언트를 열 수 있으면 `loaded`, 아니면 `error`.
- DB에 연결할 수 없으면 503 `{"status": "degraded", "chroma": ..., "database": "error", "sources": {}}`. 정상일 때 `database` 필드는 `ok`.
- OpenAI 키·`X-Internal-Token` 없이 동작한다.

---

### 6.3 소스 목록 (ai-server 내부)

- **Method / URI**: `GET /internal/v1/sources`
- **서비스**: ai-server (FastAPI)
- **인증**: `X-Internal-Token`
- **설명**: backend의 `GET /api/v1/sources` 캐시 갱신 시 호출. ACTIVE run 포인터를 ai-server가 직접 조회해서 반환.\
*(backend는 ai 스키마 테이블을 직접 읽지 않으므로 소스·활성 run 정보의 유일한 조회 경로다.)*

- 비활성(`enabled: false`) 소스도 포함한다.
- ACTIVE run이 없는(또는 포인터가 ACTIVE가 아닌 run을 가리키는) 소스는 `activeRunId`·`commitSha`·`ingestedAt`·`chunkCount`가 `null`이다.
- `ingestedAt`은 ACTIVE run의 수집 완료일(UTC 날짜)이다. ai-server는 캐시하지 않는다(backend가 60초 캐시, 정책서 §2.1).
- `framework`는 `ai.sources.framework` 값이다. backend가 공개 응답(2.1)의 `framework`를 채운다.

**응답 200**

```json
{
  "sources": [
    {
      "sourceKey":    "langchain_v03",
      "framework":    "langchain",
      "versionLabel": "v0.3",
      "displayName":  "LangChain v0.3",
      "enabled":      true,
      "activeRunId":  7,
      "commitSha":    "<COMMIT_SHA>",
      "ingestedAt":   "2026-10-05",
      "chunkCount":   3842
    }
  ],
  "comparePairs": [
    { "sourceKeyA": "langchain_v03", "sourceKeyB": "langchain_v1x" }
  ]
}
```

---

### 6.4 인덱스 파이프라인 트리거 (ai-server 내부)

- **Method / URI**: `POST /internal/v1/pipeline/ingest`
- **서비스**: ai-server (FastAPI)
- **인증**: `X-Internal-Token`
- **설명**: backend가 `POST /api/v1/admin/index/ingest/{sourceKey}` 처리 후 비동기로 호출. 수집→전처리→임베딩→검증 파이프라인 전체를 백그라운드로 실행. 완료 시 READY 상태로 전이 (ACTIVE 전환은 별도 명령).

**요청 바디**

```json
{
  "runId":       9,
  "sourceKey":   "langchain_v03",
  "acceptDrift": false
}
```

| 필드 | 설명 |
| --- | --- |
| `runId` | `ai.ingest_runs`의 PK. backend가 INSERT 후 전달 |
| `acceptDrift` | VALIDATING 게이트 청크 수 드리프트(±30% 초과) 허용 여부 |

**응답 202**

```json
{ "runId": 9, "status": "COLLECTING" }
```

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | 필드 검증 실패 |
| `SOURCE_NOT_FOUND` | 404 | sourceKey 미존재 |

---

### 6.5 인덱스 포인터 리로드 (ai-server 내부)

- **Method / URI**: `POST /internal/v1/index/reload`
- **서비스**: ai-server (FastAPI)
- **인증**: `X-Internal-Token`
- **설명**: 관리자가 `make activate-index`로 `READY → ACTIVE` 전환 완료 후 backend가 호출. ai-server의 인메모리 인덱스 포인터 캐시와 소스 메타 캐시를 즉시 무효화·재로드.

**요청 바디**

```json
{
  "sourceKey": "langchain_v03"
}
```

**응답 200**

```json
{
  "sourceKey":   "langchain_v03",
  "activeRunId": 9,
  "reloadedAt":  "2026-10-10T03:00:00Z"
}
```

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | `sourceKey` 누락 |
| `INTERNAL_UNAUTHORIZED` | 401 | `X-Internal-Token` 누락·불일치 |
| `SOURCE_NOT_FOUND` | 404 | sourceKey 미존재 |
| `SOURCE_UNAVAILABLE` | 409 | 비활성 소스 |
| `INDEX_NOT_ACTIVE` | 503 | ACTIVE run 없음 (reload 시점에 포인터 없음) |

- 활성화·롤백 CLI(`make activate-index`·`make rollback-index`)도 성공 후 이 API를 호출한다(정책서 §4.5). 호출이 실패하면 경고만 남기고, 30초 포인터 캐시 만료로 반영된다.
- `reloadedAt`은 UTC ISO-8601이다.

---

### 6.6 인덱스 현황 (ai-server 내부)

- **Method / URI**: `GET /internal/v1/index/status`
- **서비스**: ai-server (FastAPI)
- **인증**: `X-Internal-Token`
- **설명**: backend의 `GET /api/v1/admin/index/status`(§5.1)가 호출. 소스별 ACTIVE run 상세와 최근 수집 이력을 반환. ai-server는 캐시하지 않는다(관리자 화면 전용).

**응답 200**

```json
{
  "sources": [
    {
      "sourceKey":   "langchain_v03",
      "displayName": "LangChain v0.3",
      "enabled":     true,
      "activeRun": {
        "ingestRunId":      7,
        "status":           "ACTIVE",
        "commitSha":        "<COMMIT_SHA>",
        "chunkStrategy":    "C",
        "chunkCount":       3842,
        "prevChunkCount":   3790,
        "embeddingModel":   "text-embedding-3-small",
        "embeddingTokens":  2150000,
        "embeddingCostUsd": 0.042,
        "ingestDurationMs": 48500,
        "startedAt":        "2026-10-05T02:00:00Z",
        "completedAt":      "2026-10-05T02:00:48Z"
      },
      "recentRuns": [
        { "ingestRunId": 7, "status": "ACTIVE",     "startedAt": "2026-10-05T02:00:00Z" },
        { "ingestRunId": 3, "status": "FAILED",     "startedAt": "2026-09-21T02:00:00Z", "failureStage": "VALIDATING" }
      ]
    }
  ]
}
```

- 대상은 `ai.sources` 전체(카탈로그 순서)다. 비활성 소스도 넣는다.
- `activeRun`은 포인터가 가리키는 run이 `ACTIVE`일 때만 값이 있고, 아니면 null이다. 그 run의 값이 없는 필드는 null이다.
- `recentRuns`는 `ai.ingest_runs`를 `created_at` 내림차순으로 5개까지다. `failureStage`는 `FAILED`일 때만 넣는다.
- `embeddingCostUsd`는 소수(달러), 시각은 UTC ISO-8601(`Z`)이다.

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INTERNAL_UNAUTHORIZED` | 401 | `X-Internal-Token` 누락·불일치 |

---

## 부록 A. 서비스 간 내부 API 지도

| 제공 서비스 | 이용 서비스 | Method / URI | 용도 | 실패 시 처리 |
| --- | --- | --- | --- | --- |
| ai-server | backend | `POST /internal/v1/chat/stream` | RAG 질의 SSE 스트리밍 | 3초 타임아웃 → `AI_UNAVAILABLE`(503). 첫 이벤트 15초 초과 → `UPSTREAM_TIMEOUT`(504). 게스트 이용 횟수 환불 |
| ai-server | backend | `GET /internal/v1/health` | Docker Compose healthcheck, 장애 감지 | 503 시 nginx가 backend 기동 보류 |
| ai-server | backend | `GET /internal/v1/sources` | 소스 메타 캐시 갱신 (60초) | 캐시 만료 전 응답 실패 시 캐시 유지 |
| ai-server | backend | `POST /internal/v1/pipeline/ingest` | 수집·임베딩·검증 파이프라인 비동기 실행 | 호출 실패 시 ingest_run FAILED 처리 |
| ai-server | backend | `POST /internal/v1/index/reload` | ACTIVE 전환 후 ai-server 캐시 즉시 무효화 | 실패 시 경고 로그. 60초 후 캐시 자연 만료로 보완 |
| ai-server | backend | `GET /internal/v1/index/status` | 관리자 인덱스 현황(§5.1) | 실패 시 503 `AI_UNAVAILABLE` |

---

## 부록 B. SSE 이벤트 명세

> 계약 파일: `contracts/sse-events.schema.json`. backend·ai-server 계약 테스트가 동일 파일 참조.

### B.1 단일 모드 이벤트 순서

```
[스트림 시작]
  ↓
meta       — 출처·스냅샷 정보. 1회만 발행. noContext=false
  ↓
token (N회) — 텍스트 조각 스트리밍
  ↓
done       — 종결 (status: COMPLETED / PARTIAL)

[NO_CONTEXT 경로]
meta (noContext=true, sources=[]) → done (status: NO_CONTEXT)

[오류 경로]
meta → token... → error (partial: true)  // 중간 오류
     또는
error (partial: false)                     // meta 전 오류
```

### B.2 비교 모드 이벤트 순서

```
meta (A·B 양측 소스 포함) → done (status: COMPLETED, compareResult 포함)
  또는
meta (noContext=true)      → done (status: NO_CONTEXT)
```

비교 모드는 token 이벤트 없음. OpenAI Structured Outputs 결과를 검증 후 한 번에 done으로 반환.
`meta` 뒤 오류(파싱 2회 실패·30초 초과·LLM 오류)는 `error`(partial=false)로 끝난다. 종결 조건은 §6.1 "비교 모드" 표를 따른다.

### B.3 이벤트 필드 요약

| 이벤트 | 필수 필드 | 선택 필드 |
| --- | --- | --- |
| `meta` | `event`, `requestId`, `conversationId`, `messageId` | `sourceKey`, `ingestRunId`, `commitSha`, `ingestedAt`, `rewrittenQuery`, `noContext`, `sources[]` |
| `token` | `event`, `t` | — |
| `done` | `event`, `status` | `statusReason`, `finishReason`, `usage`, `latency`, `invalidCitations`, `compareResult`, `model`, `promptVersion` |
| `error` | `event`, `code`, `message`, `requestId`, `partial` | — |

### B.4 비교 모드 meta 추가 필드

```json
{
  "event":       "meta",
  "requestId":   "a1b2c3d4-...",
  "conversationId": 42,
  "messageId":   305,
  "sourceKeyA":  "langchain_v03",
  "sourceKeyB":  "langchain_v1x",
  "ingestRunIdA": 7,
  "ingestRunIdB": 8,
  "commitShaA":  "<COMMIT_SHA_A>",
  "commitShaB":  "<COMMIT_SHA_B>",
  "ingestedAtA": "2026-10-05",
  "ingestedAtB": "2026-10-05",
  "noContext":   false,
  "sources": [
    { "rank": "A1", "headingPath": "...", "permalink": "...", "siteUrl": "...", "similarity": 0.87 },
    { "rank": "B1", "headingPath": "...", "permalink": "...", "siteUrl": "...", "similarity": 0.82 }
  ]
}
```

---

## 부록 C. 상태 전이

### C.1 app.messages (ASSISTANT) 상태 전이

```
INSERT
  → PENDING
      → STREAMING  (SINGLE, meta 수신)
          → COMPLETED    [종결]
          → PARTIAL      [종결]
          → FAILED       [종결]
      → PROCESSING (COMPARE, ai-server 처리 중)
          → COMPLETED    [종결]
          → FAILED       [종결]
      → NO_CONTEXT   [종결, LOW_SIMILARITY 또는 LLM_ABSTAIN]
      → FAILED       [종결, AI_UNAVAILABLE 등]

[종결 상태: COMPLETED / PARTIAL / NO_CONTEXT / FAILED → 전이 불가 (INV-12)]
[스위퍼: STREAMING·PENDING·PROCESSING + updated_at 150초 초과 → FAILED(STALE), 종결 저장 실패분은 FAILED(PERSIST_ERROR)]
```

### C.2 app.refresh\_tokens 상태 전이

```
발급 → ACTIVE
  회전 성공 → USED
    5초 유예 내 재제출 → CONFLICT(409) 반환 (상태 변경 없음)
    5초 유예 초과 재제출 → 패밀리 전체 REVOKED
  로그아웃 · 재사용 탐지 · 초과 정리 → REVOKED
```

### C.3 ai.ingest\_runs 상태 전이

```
[신규 수집 경로]
PENDING → COLLECTING → PROCESSING → EMBEDDING → VALIDATING
  → READY   (게이트 전 항목 통과)
      → ACTIVE  (관리자 명시적 명령: make activate-index)
          → SUPERSEDED  (다음 run ACTIVE 전환 시)
              → ACTIVE      (make rollback-index, 직전 1개만)
              → PURGED      (새 SUPERSEDED 발생 시, 직전 초과분)

[S3 복원 경로]
RESTORING → VALIDATING  (tar 해제 + checksum 검증 통과)
RESTORING → FAILED      (checksum 불일치)

[실패 경로]
COLLECTING / PROCESSING / EMBEDDING → FAILED  (각 단계 오류)
VALIDATING → FAILED  (게이트 실패 · VALIDATION_TIMEOUT)
FAILED → PURGED  (24시간 경과, Python APScheduler)

PURGED → (종결)
```

> **설계 원칙:** `READY`는 검증 통과와 서비스 반영 사이의 명시적 승인 게이트. 품질 불량 인덱스를 라이브 반영 전에 차단하기 위해 `VALIDATING → ACTIVE` 직결을 허용하지 않는다.

---

## 부록 D. 토큰·쿠키 명세

### D.1 Access Token (JWT HS256)

| 항목 | 값 |
| --- | --- |
| 알고리즘 | HS256 |
| 서명 키 | 환경 변수 `JWT_SECRET` (32바이트 이상) |
| 만료 | 30분 (`exp` 클레임) |
| 시계 오차 허용 | 30초 (`clockSkew`) |
| 클레임 | `sub` (user\_id), `role`, `iat`, `exp`, `jti` (UUID v4) |
| 전달 | 응답 바디 `accessToken`. 클라이언트는 **메모리에만 보관** (localStorage 금지) |
| 키 교체 영향 | 기존 Access Token 전부 무효 → 재로그인 유도 |

### D.2 Refresh Token 쿠키

| 항목 | 값 |
| --- | --- |
| 이름 | `devdocs_rt` |
| 값 | 256비트 불투명 난수 Base64URL. DB에는 SHA-256 해시만 저장 |
| 속성 | `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` |
| `Max-Age` | 로그인 시 604800 (7일) — 패밀리 절대 만료와 동일. 회전 시에는 패밀리 남은 시간(초)으로 줄어든다(회전해도 연장 없음) |
| 로그아웃 | `Max-Age=0`으로 삭제 |

### D.3 게스트 세션 쿠키

| 항목 | 값 |
| --- | --- |
| 이름 | `devdocs_sid` |
| 값 | 128비트 난수. DB에는 SHA-256 해시만 저장 |
| 속성 | `HttpOnly; Secure; SameSite=Strict; Path=/api` |
| 발급 시점 | 게스트 최초 질문 API 호출 시 (페이지 진입만으로는 미발급) |
| TTL | 24시간 절대 만료 (사용해도 연장 없음) |

---

## 미결정 사항

| 항목 | 현재 가정값 | 결정 시점 | 영향 API |
| --- | --- | --- | --- |
| 시스템 동시 생성 상한 | 20 | W6 (11/11) E6 실험 후 | 6.1 Semaphore, 0.7 rate limit 표 |

---

end.
