# API 명세서

> 최종 수정일: 2026-11-01

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
| `INVALID_REQUEST` | 400 | 공통 | Bean Validation 실패. `details[]`에 필드별 사유 포함 |
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
| `AUTH_REFRESH_INVALID` | 401 | DB 미존재 | 로그인 화면 |
| `AUTH_REFRESH_EXPIRED` | 401 | 패밀리 7일 만료 | 로그인 화면 |
| `AUTH_REFRESH_REUSED` | 401 | 5초 유예 이후 USED 재제출 → 패밀리 전체 REVOKED | "보안을 위해 로그아웃되었습니다" |
| `AUTH_REFRESH_CONFLICT` | 409 | 5초 유예 내 재제출 (다중 탭 경합) | 1회 재시도 (단일 Promise 직렬화) |

**동시성 보장**

- 유예 5초 이내 USED 토큰 재제출 → `AUTH_REFRESH_CONFLICT`(409). 브라우저 쿠키는 이미 새 토큰이므로 1회 재시도하면 성공.
- 5초 초과 USED 재제출 → 탈취로 간주, 패밀리 전체 REVOKED, 쿠키 `Max-Age=0` 삭제.

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
**대응 테이블**: `ai.sources` (읽기 전용), `ai.index_pointers` (읽기 전용), `ai.compare_pairs` (읽기 전용)\
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
    ]
  }
}
```

| 필드 | 설명 |
| --- | --- |
| `sources[]` | enabled=true AND ACTIVE run 존재 소스만 포함 |
| `activeRun.ingestedAt` | YYYY-MM-DD (UTC 기준 수집 완료일) |
| `comparePairs[].compareEnabled` | 양측 소스가 모두 enabled=true AND ACTIVE run 존재일 때 true |

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `INDEX_NOT_ACTIVE` | 503 | enabled 소스가 존재하나 ACTIVE run 없음 (장애 상태) |

**프론트 계약**

- 앱 시작 시 이 API 1회 호출 → `sources`로 버전 선택 드롭다운 구성, `comparePairs[0].compareEnabled`로 비교 탭 활성화/비활성화 결정.
- 하드코딩 버전 목록 사용 금지 (UI-01).

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
  "sourceKeyB":     null
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

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
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

**비교 모드 ASSISTANT 메시지 추가 필드**

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

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `AUTH_TOKEN_MISSING` | 401 | JWT 없음 |
| `AUTH_TOKEN_EXPIRED` | 401 | Access Token 만료 |
| `CONVERSATION_NOT_FOUND` | 404 | 없는 대화 또는 타인 대화 (INV-14) |

## 5. 관리자 (Admin)

> **서비스**: backend (Spring Boot)\
**인증**: JWT + `ROLE_ADMIN` 필수. 비관리자 → `FORBIDDEN`(403)\
**대응 테이블**: `ai.sources`, `ai.ingest_runs`, `ai.index_pointers` (읽기), `app.messages` (집계)

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

**에러**

| 코드 | HTTP | 조건 |
| --- | --- | --- |
| `AUTH_TOKEN_MISSING` | 401 | JWT 없음 |
| `FORBIDDEN` | 403 | ROLE\_USER 접근 |

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
| `acceptDrift` | boolean | false | VALIDATING 게이트에서 청크 수 드리프트(>10%) 허용 시 true |

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

## 6. 내부 API (ai-server · FastAPI)

> **서비스**: ai-server (Python FastAPI + uvicorn)\
**Base URL**: `http://ai-server:8001` (Docker Compose 내부망 전용)\
**노출 범위**: 외부 인터넷 미노출. nginx에서 `/internal/**` 차단\
**인증**: 내부망 신뢰. 별도 토큰 없음\
**FastAPI 문서**: `/docs` — local·staging 프로필만 노출 (prod 비노출, 9.1 참고)

---

### 6.1 스트리밍 질의

- **Method / URI**: `POST /internal/v1/chat/stream`
- **서비스**: ai-server (FastAPI)
- **인증**: 내부망 전용
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
| `history` | 최근 3턴 (USER·ASSISTANT 쌍). 첫 질문이면 빈 배열 `[]` |
| `promptVersion` | `prompts/` 디렉터리 파일명. backend가 환경 변수로 주입 |

**응답**: `200 OK`, `text/event-stream`

```
data: {"event":"meta", "requestId":"a1b2c3d4", "sourceKey":"langchain_v03", "ingestRunId":7, "commitSha":"<COMMIT_SHA>", "ingestedAt":"2026-10-05", "rewrittenQuery":"Agent 생성 방법", "noContext":false, "sources":[...]}

data: {"event":"token", "t":"LangChain v0.3에서 "}

data: {"event":"done", "status":"COMPLETED", "finishReason":"stop", "usage":{"prompt":1240,"completion":312}, "latency":{"rewriteMs":450,"embedMs":80,"retrieveMs":120,"ttftMs":1850,"totalMs":5300}, "invalidCitations":[]}
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
| `INVALID_REQUEST` | 400 | 필드 검증 실패 (Pydantic) |
| `INDEX_NOT_ACTIVE` | 503 | ACTIVE run 없음 (INV-01) |
| `AI_BUSY` | 503 | asyncio Semaphore 소진 |

**에러 (스트림 후)**: `event: error` SSE 이벤트

```json
{ "event": "error", "code": "LLM_ERROR", "message": "LLM 오류가 발생했습니다.", "request_id": "a1b2c3d4", "partial": false }
```

**처리 파이프라인 (ai-server 내부)**

1. 요청 검증 (Pydantic) + Semaphore 획득
2. 질의 재작성 — `history` 존재 시 LLM 호출, 첫 질문이면 SKIPPED
3. 임베딩 — `text-embedding-3-small`
4. 벡터 검색 — Chroma PersistentClient, top-K, cosine. INV-02 2차 메타데이터 검증
5. 유사도 < τ → NO\_CONTEXT (meta + done 즉시 반환, LLM 미호출)
6. 프롬프트 조립 + OpenAI 스트리밍 호출 (temperature 0, max\_tokens 1024)
7. ai-server가 첫 16자 버퍼링 → sentinel `[[NO_ANSWER]]` 감지 시 NO\_CONTEXT 종결
8. token 이벤트 스트리밍 → done 이벤트
9. Semaphore 해제

---

### 6.2 헬스체크

- **Method / URI**: `GET /internal/v1/health`
- **서비스**: ai-server (FastAPI)
- **인증**: 내부망 전용
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

---

### 6.3 소스 목록 (ai-server 내부)

- **Method / URI**: `GET /internal/v1/sources`
- **서비스**: ai-server (FastAPI)
- **인증**: 내부망 전용
- **설명**: backend의 `GET /api/v1/sources` 캐시 갱신 시 호출. ACTIVE run 포인터를 ai-server가 직접 조회해서 반환.\
*(backend가 `ai.sources` + `ai.index_pointers`를 직접 읽기 가능한 경우 이 API를 생략할 수 있음. 스키마 분리 원칙상 ai-server를 통한 조회가 더 명확함.)*

**응답 200**

```json
{
  "sources": [
    {
      "sourceKey":    "langchain_v03",
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
- **인증**: 내부망 전용
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
| `acceptDrift` | VALIDATING 게이트 청크 수 드리프트(>10%) 허용 여부 |

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
- **인증**: 내부망 전용
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
| `SOURCE_NOT_FOUND` | 404 | sourceKey 미존재 |
| `INDEX_NOT_ACTIVE` | 503 | ACTIVE run 없음 (reload 시점에 포인터 없음) |

---

## 부록 A. 서비스 간 내부 API 지도

| 제공 서비스 | 이용 서비스 | Method / URI | 용도 | 실패 시 처리 |
| --- | --- | --- | --- | --- |
| ai-server | backend | `POST /internal/v1/chat/stream` | RAG 질의 SSE 스트리밍 | 3초 타임아웃 → `AI_UNAVAILABLE`(503). 첫 이벤트 15초 초과 → `UPSTREAM_TIMEOUT`(504). 게스트 이용 횟수 환불 |
| ai-server | backend | `GET /internal/v1/health` | Docker Compose healthcheck, 장애 감지 | 503 시 nginx가 backend 기동 보류 |
| ai-server | backend | `GET /internal/v1/sources` | 소스 메타 캐시 갱신 (60초) | 캐시 만료 전 응답 실패 시 캐시 유지 |
| ai-server | backend | `POST /internal/v1/pipeline/ingest` | 수집·임베딩·검증 파이프라인 비동기 실행 | 호출 실패 시 ingest_run FAILED 처리 |
| ai-server | backend | `POST /internal/v1/index/reload` | ACTIVE 전환 후 ai-server 캐시 즉시 무효화 | 실패 시 경고 로그. 60초 후 캐시 자연 만료로 보완 |

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

### B.3 이벤트 필드 요약

| 이벤트 | 필수 필드 | 선택 필드 |
| --- | --- | --- |
| `meta` | `event`, `requestId`, `conversationId`, `messageId` | `sourceKey`, `ingestRunId`, `commitSha`, `ingestedAt`, `rewrittenQuery`, `noContext`, `sources[]` |
| `token` | `event`, `t` | — |
| `done` | `event`, `status` | `statusReason`, `finishReason`, `usage`, `latency`, `invalidCitations`, `compareResult` |
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
[스위퍼: STREAMING + updated_at 150초 초과 → FAILED(STALE)]
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
| `Max-Age` | 604800 (7일) — 패밀리 절대 만료와 동일 |
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
| NO\_CONTEXT 임계값 τ | 0.30 (개발용) | W2 (10/14) E1 실험 후 | 3.1 chat/stream, 6.1 내부 스트림 |
| Top-K | 5 | W3 (10/21) E2 실험 후 | 6.1 내부 스트림 요청 파라미터 |
| 청킹 전략 | 전략 B | W3 (10/21) E2 실험 후 | 5.1 admin 대시보드 chunkStrategy 필드 |
| 시스템 동시 생성 상한 | 20 | W6 (11/11) E6 실험 후 | 6.1 Semaphore, 0.7 rate limit 표 |
| 내부 소스 조회 방식 | ai-server GET `/internal/v1/sources` 경유 | 구현 시 결정 | 6.3 필요 여부 |

---

end.
