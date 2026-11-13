# 시스템 아키텍처 다이어그램

> 수정일: 2026-11-06

---

## 0. 공통 규칙

### 0.1 다이어그램 규칙

| 규칙 | 내용 |
| --- | --- |
| 도구 | Mermaid 전용. 흐름 = `sequenceDiagram`, 상태 = `stateDiagram-v2`, 판정·분기 = `flowchart TD` |
| 필수 경로 | 정상 흐름만 그리지 않는다. 실패·경합·중복 경로를 `alt`/`opt`/`loop`으로 함께 표시 |
| 참여자 약어 | `U`(User/React), `BE`(Spring Boot), `DB`(PostgreSQL), `AI`(FastAPI), `VDB`(Chroma), `LLM`(OpenAI API), `GH`(GitHub API) |
| 표기 규칙 | SSE 이벤트는 `[SSE]` 접두 표기, DB 트랜잭션은 `BEGIN`/`COMMIT` 명시, 불변식 참조는 Note 또는 설명 줄에 `INV-N` 표기 |
| 캡션 형식 | `### N.M 제목 — 부제목` |

---

## 1. 시스템 구성도

> 작성: 1인 프로젝트
>
- [x] 메모 섹션 → 정식 문서 이관 완료

### 1.1 Docker Compose 배포 단위

```mermaid
graph TB
    subgraph Client
        FE[React SPA]
    end

    subgraph "Docker Compose Network"
        N[nginx\n리버스 프록시·Rate Limit·SSE 중계]
        BE["Spring Boot\n인증·이력·프록시 (app 스키마 소유)"]
        AI["FastAPI\nRAG 파이프라인 (ai 스키마 소유)"]
        VDB[("Chroma\nVector DB")]
        RDB[("PostgreSQL\napp + ai 스키마")]
    end

    subgraph External
        OAI["OpenAI API\nEmbedding + LLM"]
        GH["GitHub API\n.mdx 원본 수집"]
        S3["Amazon S3\nDB 백업 + 인덱스 스냅샷"]
    end

    FE -->|"HTTPS"| N
    N -->|"REST / SSE\n/api/v1/**"| BE
    N -->|"/internal/** 차단"| AI
    BE -->|"WebClient Non-blocking\nPOST /internal/v1/chat/stream"| AI
    BE -->|"Flyway 마이그레이션\napp 스키마 읽기·쓰기"| RDB
    AI -->|"Alembic 마이그레이션\nai 스키마 읽기·쓰기"| RDB
    BE -->|"ai.sources·index_pointers 읽기만"| RDB
    AI --> VDB
    AI -->|"임베딩·생성 API"| OAI
    AI -.->|"오프라인 수집 (로컬·스테이징 전용)"| GH
    RDB -.->|"pg_dump 일 1회 KST 03:00"| S3
    AI -.->|"스냅샷 tar.gz 저장·복원"| S3
```

- **컨테이너 5개:** nginx, backend(Spring Boot), ai-server(FastAPI), chroma, postgres — `docker-compose up`으로 통합 실행
- **네트워크 경계:** nginx만 외부 노출. ai-server `/internal/**`는 nginx에서 차단 — 외부에서 직접 접근 불가
- **스키마 소유권:** `app` 스키마 = backend 독점 쓰기, `ai` 스키마 = ai-server 독점 쓰기. backend는 `ai.sources`, `ai.index_pointers` 읽기만 허용

---

### 1.2 논리 아키텍처 (계층별 책임)

```mermaid
graph LR
    subgraph "Presentation"
        A["React SPA\nSSE 스트림 파싱\n출처 카드 렌더링"]
    end
    subgraph "Application / Business (Java)"
        B["Spring Boot\nJWT 인증·게스트 세션·이용량 제어\n대화·메시지·출처 영구 보존\nai-server 프록시 (WebClient)"]
    end
    subgraph "AI / RAG (Python)"
        C["FastAPI\n질의 재작성·임베딩·벡터 검색\n프롬프트 조립·LLM 스트리밍\n인덱스 수집·검증·활성화"]
    end
    subgraph "Data"
        D[("PostgreSQL\napp: 사용자·토큰·대화·메시지\nai: 소스·수집이력·인덱스포인터")]
        E[("Chroma\n버전별 컬렉션\n청크 임베딩 저장")]
    end

    A -->|"REST / SSE"| B
    B -->|"SSE 중계\nPOST /internal/v1/chat/stream"| C
    B -->|"app 스키마 R/W\nai 스키마 R only"| D
    C -->|"ai 스키마 R/W"| D
    C -->|"컬렉션 CRUD"| E
```

---

## 2. 인증·토큰

> 작성: 1인 프로젝트
>
- [ ] USED 유예 경합(409) 재시도 루프 단위 테스트 작성 필요

### 2.1 시퀀스 — 토큰 회전·재사용 탐지

```mermaid
sequenceDiagram
    participant U as Client
    participant BE as Spring Boot
    participant DB as PostgreSQL

    U->>BE: POST /api/v1/auth/refresh<br/>(Cookie: devdocs_rt=RAW_TOKEN)
    BE->>DB: SELECT rt.id, rt.status, rt.updated_at,<br/>tf.expires_at, tf.status AS family_status<br/>FROM refresh_tokens rt JOIN token_families tf<br/>ON rt.family_id = tf.id<br/>WHERE rt.token_hash = SHA256(RAW_TOKEN)<br/>FOR UPDATE OF rt

    alt 토큰 미존재 또는 패밀리 REVOKED
        DB-->>BE: (no row) or family_status=REVOKED
        BE-->>U: 401 AUTH_TOKEN_MISSING
    else 패밀리 expires_at 만료
        DB-->>BE: row (family_status=ACTIVE, tf.expires_at 경과)
        BE->>DB: UPDATE token_families SET status=REVOKED WHERE id=?
        BE-->>U: 401 AUTH_TOKEN_EXPIRED + Set-Cookie: devdocs_rt=; Max-Age=0
    else USED — 유예 5초 이내 재제출 (다중 탭 경합)
        DB-->>BE: row (rt.status=USED, rt.updated_at > NOW()-5s)
        BE-->>U: 409 AUTH_REFRESH_CONFLICT
        Note over U: 쿠키는 이미 새 토큰 보유.<br/>클라이언트 1회 재시도 (single-flight Promise)
    else USED — 유예 5초 초과 (재사용 탐지)
        DB-->>BE: row (rt.status=USED, rt.updated_at ≤ NOW()-5s)
        Note over BE: INV-15 위반 탐지 → 패밀리 전체 REVOKE
        BE->>DB: UPDATE refresh_tokens SET status=REVOKED<br/>WHERE family_id=? [패밀리 전체]
        BE->>DB: UPDATE token_families SET status=REVOKED WHERE id=?
        BE-->>U: 401 AUTH_REFRESH_REUSED + Set-Cookie: devdocs_rt=; Max-Age=0
    else ACTIVE — 정상 회전
        DB-->>BE: row (rt.status=ACTIVE, tf.expires_at 유효)
        BE->>DB: BEGIN
        BE->>DB: UPDATE refresh_tokens SET status=USED,<br/>updated_at=NOW() WHERE id=? [기존 ACTIVE → USED]
        BE->>DB: INSERT refresh_tokens (new_hash, ACTIVE, family_id)
        BE->>DB: COMMIT
        Note over DB: 트랜잭션 내 INV-15 보장:<br/>ACTIVE 1개 → USED, 신규 ACTIVE 1개
        BE->>BE: generateAccessToken(user_id, role, jti=UUID)
        BE-->>U: 200 {accessToken} + Set-Cookie: devdocs_rt=NEW_TOKEN
    end
```

---

### 2.2 상태 전이 — token_families

```mermaid
stateDiagram-v2
    direction LR
    [*] --> ACTIVE : 로그인 (패밀리 생성)
    ACTIVE --> REVOKED : 로그아웃 / 재사용 탐지 / 동시 10개 초과
    REVOKED --> [*] : GC — expires_at+1일 물리삭제
    ACTIVE --> [*] : GC — expires_at+1일 물리삭제
```

---

### 2.3 상태 전이 — refresh_tokens

```mermaid
stateDiagram-v2
    direction LR
    [*] --> ACTIVE : 발급 (로그인·회전 성공)
    ACTIVE --> USED : 회전 성공\n[기존 ACTIVE → USED, 신규 ACTIVE INSERT]
    ACTIVE --> REVOKED : 로그아웃 / 재사용 탐지 / 패밀리 REVOKE
    USED --> REVOKED : 5초 초과 재제출 탐지 / 패밀리 REVOKE
    REVOKED --> [*] : GC — 패밀리 expires_at+1일 물리삭제
    ACTIVE --> [*] : GC — 패밀리 expires_at+1일 물리삭제
    USED --> [*] : GC — 패밀리 expires_at+1일 물리삭제
```

> **USED 5초 이내 재제출** → 상태 변경 없이 409 CONFLICT 반환. 자기 전이(USED→USED)가 아니라 응답만 분기되는 런타임 판정임.

---

## 3. 게스트 세션

> 작성: 1인 프로젝트
>
- [ ] 전시회 당일 IP당 신규 세션 30→60 조정 반영 확인

### 3.1 상태 전이 — guest_sessions

```mermaid
stateDiagram-v2
    direction LR
    [*] --> ACTIVE : 최초 질문 API 호출 시 발급\n(페이지 진입만으로는 미발급)
    ACTIVE --> ACTIVE : used_count 차감 (원자적 UPDATE)\n[used_count < 5 AND expires_at > NOW()]
    ACTIVE --> EXHAUSTED : used_count=5 도달
    EXHAUSTED --> ACTIVE : 서버 오류 환불\n(meta 이전, 서버 측 원인만)
    ACTIVE --> [*] : GC — expires_at+24h 물리삭제
    EXHAUSTED --> [*] : GC — expires_at+24h 물리삭제
```

> **원자적 차감:** `UPDATE guest_sessions SET used_count=used_count+1 WHERE sid_hash=? AND used_count < 5 AND expires_at > NOW()`. 영향 행 0 → 429 GUEST_QUOTA_EXCEEDED.

---

## 4. 이용량

> 작성: 1인 프로젝트
>
- [ ] idx_messages_user_role_created 복합 인덱스 생성 확인 필요

> **스케줄러 없음.** 일일 할당량은 `messages.quota_cost` SUM COUNT 방식(런타임 판정). `KST 00:00 초기화`는 `created_at >= KST 오늘 00:00` 조건으로 자동 달성. 별도 배치 초기화 불필요.

### 4.1 판정 — 일일 이용량 검사·차감

```mermaid
flowchart TD
    START([질문 요청]) --> AUTH{인증 유형?}

    AUTH -- 게스트 --> G_ATOMIC["원자적 차감\nUPDATE guest_sessions\nSET used_count=used_count+1\nWHERE sid_hash=?\nAND used_count < 5\nAND expires_at > NOW()"]
    G_ATOMIC -- "영향 행 0" --> G_QUOTA["429\nGUEST_QUOTA_EXCEEDED"]
    G_ATOMIC -- "영향 행 1" --> PROCEED["요청 처리 진행\n→ ai-server 호출"]

    AUTH -- "로그인 사용자" --> DELTA{"mode?"}
    DELTA -- SINGLE --> D1["delta = 1"]
    DELTA -- COMPARE --> D2["delta = 2"]

    D1 --> U_COUNT["SELECT SUM(quota_cost)\nFROM messages\nWHERE user_id=?\nAND role='USER'\nAND created_at >= KST_TODAY_00:00"]
    D2 --> U_COUNT

    U_COUNT --> U_CHECK{"today_used + delta > 100?"}
    U_CHECK -- Yes --> U_QUOTA["429\nDAILY_QUOTA_EXCEEDED"]
    U_CHECK -- No --> RATE_CHECK{"분당 10회 초과?"}
    RATE_CHECK -- Yes --> RATE_LIMIT["429\nRATE_LIMITED\n+ Retry-After"]
    RATE_CHECK -- No --> CONCUR_CHECK{"동시 스트림 초과?\nUSER≤2 / GUEST≤1"}
    CONCUR_CHECK -- Yes --> CONCUR_LIMIT["429\nCONCURRENT_STREAM_LIMIT"]
    CONCUR_CHECK -- No --> PROCEED
```

> **COUNT 쿼리 최적화:** `(user_id, role, created_at DESC)` 복합 인덱스 필수. 일일 최대 100회 제한으로 스캔 범위가 작아 t3.small에서도 충분.
> **자정 경계:** `created_at >= DATE_TRUNC('day', NOW() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'`으로 KST 기준 정확히 판정.

---

## 5. 질의응답·메시지

> 작성: 1인 프로젝트
>
- [ ] 스위퍼와 done 이벤트 동시 UPDATE 충돌 시나리오 단위 테스트 작성 필요

### 5.1 시퀀스 — 단일 모드 질의응답

```mermaid
sequenceDiagram
    participant U as User
    participant BE as Spring Boot
    participant DB as PostgreSQL
    participant AI as FastAPI
    participant VDB as Chroma
    participant LLM as OpenAI

    U->>BE: POST /api/v1/chat {question, sourceKey, conversationId?}
    BE->>DB: 이용량 확인 (SUM quota_cost WHERE today)<br/>INV-11 검사: SELECT FOR UPDATE
    BE->>DB: BEGIN<br/>INSERT messages(USER, quota_cost=1)<br/>INSERT messages(ASSISTANT, PENDING)<br/>COMMIT

    BE->>AI: POST /internal/v1/chat/stream [WebClient, 연결 타임아웃 3s]

    alt AI 연결 실패 (3초 초과)
        AI-->>BE: connection timeout
        BE->>DB: UPDATE messages SET status=FAILED,<br/>status_reason=AI_UNAVAILABLE
        opt 게스트 요청
            BE->>DB: UPDATE guest_sessions SET used_count=used_count-1<br/>WHERE sid_hash=? AND used_count > 0
            Note over BE: 환불 조건: meta 이전 + 서버 측 원인
        end
        BE-->>U: 503 AI_UNAVAILABLE
    else 연결 성공
        opt 멀티턴 — 2번째 이상 질문 (history 존재)
            AI->>LLM: rewrite(question, history 최근 3턴) [≤3초]
            alt 재작성 성공
                LLM-->>AI: rewritten_query (≤200자)
                Note over AI: rewrite_status=OK
            else 3초 초과·빈 출력·200자 초과
                AI->>AI: 원 질문으로 폴백
                Note over AI: rewrite_status=FALLBACK
            end
        end

        AI->>AI: embed(query) [text-embedding-3-small, ≤5초, 재시도 1회]
        AI->>VDB: search(vector, collection=sourceKey_activeRunId, top_k=K)
        Note over VDB: INV-02: 결과 메타데이터 2차 검증<br/>version·ingest_run_id 불일치 청크 폐기
        VDB-->>AI: Top-K chunks + similarity scores

        alt top-1 similarity < τ — LOW_SIMILARITY
            Note over AI: INV-07: LLM 미호출
            AI-->>BE: [SSE] meta(noContext=true, sources=[])
            AI-->>BE: [SSE] done(status=NO_CONTEXT, reason=LOW_SIMILARITY)
            BE->>DB: UPDATE messages SET status=NO_CONTEXT,<br/>status_reason=LOW_SIMILARITY
            BE-->>U: [SSE] meta + done
        else similarity ≥ τ — 검색 통과
            AI-->>BE: [SSE] meta(sources, ingestRunId, commitSha, rewrittenQuery)
            BE->>DB: UPDATE messages SET status=STREAMING
            BE->>DB: INSERT message_sources(rank, heading_path, permalink, similarity) [스냅샷]
            BE-->>U: [SSE] meta

            AI->>LLM: chat completion stream [temperature=0, max_tokens=1024]
            Note over AI: 첫 16자 버퍼링 → sentinel 감지 대기

            alt 첫 이벤트(meta) 15초 초과 or 첫 토큰 10초 초과
                BE->>DB: UPDATE messages SET status=FAILED,<br/>status_reason=UPSTREAM_TIMEOUT
                opt 게스트 요청
                    BE->>DB: used_count-1 [환불]
                end
                BE-->>U: 504 UPSTREAM_TIMEOUT
            else LLM_ABSTAIN — sentinel 감지
                LLM-->>AI: [[NO_ANSWER]] 첫 16자
                AI->>AI: 토큰 차단 (클라이언트에 미전송)
                AI-->>BE: [SSE] done(status=NO_CONTEXT, reason=LLM_ABSTAIN)
                BE->>DB: UPDATE messages SET status=NO_CONTEXT,<br/>status_reason=LLM_ABSTAIN
                BE-->>U: [SSE] done
            else 정상 스트리밍
                loop token 이벤트 (N회, 하트비트 10초)
                    LLM-->>AI: token 조각
                    AI-->>BE: [SSE] {"event":"token","t":"..."}
                    BE-->>U: [SSE] token (메모리 버퍼 누적, DB 미기록)
                end

                alt 클라이언트 연결 끊김
                    U->>BE: connection abort (탭 닫기·네트워크 단절)
                    BE->>AI: WebClient 구독 해제 [취소 전파]
                    BE->>DB: UPDATE messages SET status=PARTIAL or FAILED,<br/>status_reason=CLIENT_ABORTED
                    Note over BE: 게스트 환불 없음 (meta 이후)
                else 유휴 타임아웃 (30초) 또는 최대 시간 (120초) 초과
                    BE->>AI: 구독 해제
                    BE->>DB: UPDATE → PARTIAL(MAX_DURATION) or PARTIAL(UPSTREAM_IDLE_TIMEOUT)
                    BE-->>U: [SSE] error(partial=true)
                else LLM 오류 (스트림 중)
                    LLM-->>AI: error
                    AI-->>BE: [SSE] error(code=LLM_ERROR, partial=true or false)
                    BE->>DB: UPDATE → PARTIAL(LLM_ERROR) or FAILED(LLM_ERROR)
                    BE-->>U: [SSE] error
                else 정상 완료
                    LLM-->>AI: finish_reason=stop
                    AI-->>BE: [SSE] done(status=COMPLETED, usage, latency, invalidCitations)
                    BE->>DB: UPDATE messages SET status=COMPLETED,<br/>content=버퍼, usage, prompt_version, finish_reason
                    Note over DB: INV-08: invalidCitations 기록
                    BE-->>U: [SSE] done
                end
            end
        end
    end
```

---

### 5.2 시퀀스 — 버전 비교 모드

```mermaid
sequenceDiagram
    participant U as User
    participant BE as Spring Boot
    participant DB as PostgreSQL
    participant AI as FastAPI
    participant VDB as Chroma
    participant LLM as OpenAI

    U->>BE: POST /api/v1/chat/compare<br/>{question, sourceKeyA, sourceKeyB}
    Note over BE: 게스트 → 403 GUEST_MODE_NOT_ALLOWED (INV-16)
    BE->>DB: 이용량 확인 (delta=2) + INV-11 검사
    BE->>DB: INSERT messages(USER, quota_cost=2)<br/>INSERT messages(ASSISTANT, PENDING)

    BE->>AI: POST /internal/v1/chat/stream<br/>{mode=COMPARE, sourceKeyA, sourceKeyB, question}

    alt AI 연결 실패
        AI-->>BE: 503
        BE->>DB: UPDATE → FAILED(AI_UNAVAILABLE)
        BE-->>U: 503 AI_UNAVAILABLE
    else 연결 성공
        AI->>AI: embed(question)

        par A측 검색
            AI->>VDB: search(vector, collection=sourceKeyA_runIdA, top_k=K)
            VDB-->>AI: A chunks + scores
        and B측 검색
            AI->>VDB: search(vector, collection=sourceKeyB_runIdB, top_k=K)
            VDB-->>AI: B chunks + scores
        end

        alt 양측 top-1 모두 < τ
            AI-->>BE: [SSE] meta(noContext=true)
            AI-->>BE: [SSE] done(status=NO_CONTEXT, reason=LOW_SIMILARITY)
            BE->>DB: UPDATE → NO_CONTEXT(LOW_SIMILARITY)
            BE-->>U: [SSE] meta + done
        else 검색 통과
            AI-->>BE: [SSE] meta(sourceKeyA, sourceKeyB, A·B sources, commitShaA, commitShaB)
            BE->>DB: UPDATE → PROCESSING
            BE->>DB: INSERT message_sources(A측 + B측, rank=A1..AN, B1..BN) [스냅샷]
            BE-->>U: [SSE] meta

            AI->>LLM: chat completion [Structured Outputs JSON 스키마, ≤30초]
            Note over AI: token 이벤트 없음 — JSON 검증 후 한 번에 반환

            alt 30초 초과
                AI-->>BE: error(UPSTREAM_TIMEOUT)
                BE->>DB: UPDATE → FAILED(UPSTREAM_TIMEOUT)
                BE-->>U: 504 UPSTREAM_TIMEOUT
            else JSON 파싱 2회 연속 실패
                AI->>LLM: 재시도 1회 포함 총 2회
                LLM-->>AI: invalid JSON (2회)
                AI-->>BE: error(COMPARE_PARSE_ERROR)
                BE->>DB: UPDATE → FAILED(COMPARE_PARSE_ERROR)
                BE-->>U: 502 COMPARE_PARSE_ERROR
            else 정상 완료
                LLM-->>AI: compareResult JSON<br/>{versionA, versionB, diff, citationsA[], citationsB[]}
                AI->>AI: INV-08: 인용 번호 범위 검증
                AI-->>BE: [SSE] done(status=COMPLETED, compareResult, invalidCitations)
                BE->>DB: UPDATE → COMPLETED<br/>INSERT compare_results
                BE-->>U: [SSE] done + compareResult
            end
        end
    end
```

---

### 5.3 상태 전이 — app.messages (ASSISTANT)

```mermaid
stateDiagram-v2
    direction TB

    [*] --> PENDING : INSERT (요청 검증·이용량 통과)

    PENDING --> STREAMING : [단일] meta 수신
    PENDING --> PROCESSING : [비교] ai-server 호출 시작
    PENDING --> NO_CONTEXT : top-1 < τ (LOW_SIMILARITY)\nINV-07: LLM 미호출
    PENDING --> FAILED : AI_UNAVAILABLE · UPSTREAM_TIMEOUT\nLLM_ERROR · CLIENT_ABORTED

    STREAMING --> COMPLETED : finish_reason=stop
    STREAMING --> PARTIAL : 토큰 ≥ 1 후 중단\nCLIENT_ABORTED · LLM_ERROR\nMAX_DURATION · LENGTH · UPSTREAM_IDLE_TIMEOUT
    STREAMING --> NO_CONTEXT : sentinel 감지 (LLM_ABSTAIN)
    STREAMING --> FAILED : 토큰 = 0 중단 · 150초 고착\nSTALE · PERSIST_ERROR

    PROCESSING --> COMPLETED : JSON 검증 완료
    PROCESSING --> NO_CONTEXT : 양측 top-1 < τ
    PROCESSING --> FAILED : 30초 초과 · 파싱 2회 실패 · AI오류

    COMPLETED --> [*]
    PARTIAL --> [*]
    NO_CONTEXT --> [*]
    FAILED --> [*]
```

> **INV-12:** 종결 상태 4개(COMPLETED·PARTIAL·NO_CONTEXT·FAILED)에서 나가는 전이 없음. `canTransition(from, to)` 단위 테스트 필수.

---

## 6. 인덱스 관리

> 작성: 1인 프로젝트
>
- [ ] VALIDATING 게이트 10분 제한 타임아웃 구현 방식 확인 필요

### 6.1 시퀀스 — 수집 트리거·활성화

```mermaid
sequenceDiagram
    participant Admin
    participant BE as Spring Boot
    participant DB as PostgreSQL
    participant AI as FastAPI
    participant GH as GitHub API
    participant VDB as Chroma

    Note over Admin,BE: prod 프로필 → 403 FORBIDDEN_IN_PROFILE (RAG-10)
    Admin->>BE: POST /api/v1/admin/ingest/{sourceKey}<br/>{acceptDrift: false}
    BE->>DB: INSERT ai.ingest_runs(status=PENDING, source_key)
    BE-->>Admin: 202 {ingestRunId: N}
    BE->>AI: POST /internal/v1/pipeline/ingest {runId, sourceKey} [비동기 위임]

    AI->>DB: UPDATE ingest_runs SET status=COLLECTING
    AI->>GH: sparse checkout .mdx (commit SHA 고정)

    alt GitHub API 오류 / 타임아웃
        GH-->>AI: 4xx / timeout
        AI->>DB: UPDATE ingest_runs SET status=FAILED,<br/>failure_stage=COLLECTING, failure_reason=?
        Note over AI: 기존 ACTIVE 인덱스 유지 (RAG-10)
    else 수집 성공
        GH-->>AI: .mdx 파일 + commit_sha
        AI->>DB: UPDATE ingest_runs SET status=PROCESSING, commit_sha=?

        AI->>AI: Source Adapter 전처리·섹션분리·청킹<br/>(v0.3: :::js 제거, v1.x: 노트북 직렬화)

        AI->>DB: UPDATE ingest_runs SET status=EMBEDDING
        AI->>AI: embed chunks [text-embedding-3-small, 재시도 1회]

        alt 임베딩 실패 (재시도 포함)
            AI->>DB: UPDATE ingest_runs SET status=FAILED,<br/>failure_stage=EMBEDDING
            Note over AI: 기존 ACTIVE 인덱스 유지
        else 임베딩 성공
            AI->>VDB: 청크 저장 (collection=sourceKey_runN)
            AI->>DB: UPDATE ingest_runs SET status=VALIDATING

            AI->>AI: 검증 게이트 실행 (≤10분)<br/>① 청크 수 드리프트 <10% (acceptDrift=false 시)<br/>② 스모크 쿼리 5문항 통과<br/>③ permalink 100% 자동 검증

            alt 게이트 실패 또는 10분 초과 (VALIDATION_TIMEOUT)
                AI->>DB: UPDATE ingest_runs SET status=FAILED,<br/>failure_stage=VALIDATING
                Note over VDB: 컬렉션 보관 → 24시간 후 PURGE 스케줄러가 삭제
                Note over AI: 기존 ACTIVE 인덱스 유지 (RAG-10)
            else 게이트 전 항목 통과
                AI->>DB: UPDATE ingest_runs SET status=READY
                AI-->>BE: 완료 콜백 (doc_count, chunk_count, validation_report)
            end
        end
    end

    Admin->>BE: GET /api/v1/admin/index/status [폴링]
    BE-->>Admin: {sourceKey, activeRunId, status, docCount, lastBuiltAt}

    Note over Admin: make activate-index RUN=N (로컬·스테이징, READY → ACTIVE)
    Admin->>DB: BEGIN<br/>UPDATE ingest_runs SET status=SUPERSEDED WHERE source_key=? AND status=ACTIVE<br/>UPDATE ingest_runs SET status=ACTIVE WHERE id=N<br/>UPDATE index_pointers SET active_run_id=N WHERE source_key=?<br/>COMMIT
    Note over DB: INV-01 보장: 단일 트랜잭션으로 ACTIVE 교체
    Admin->>AI: POST /internal/v1/index/reload [캐시 즉시 무효화]
    AI->>AI: 포인터 캐시 재로드 + 메타 API 캐시 무효화

    opt 이전 SUPERSEDED가 있으면 PURGED 처리
        AI->>VDB: 이전 SUPERSEDED 컬렉션 삭제
        AI->>DB: UPDATE ingest_runs SET status=PURGED WHERE status=SUPERSEDED<br/>AND source_key=? AND id != (직전 1개)
        Note over AI: 직전 1개만 보관 — 롤백 대비
    end
```

---

### 6.2 상태 전이 — ai.ingest_runs

```mermaid
stateDiagram-v2
    direction TB

    [*] --> PENDING : make ingest\n(로컬·스테이징 전용)
    [*] --> RESTORING : make restore-index\n(모든 프로필)

    PENDING --> COLLECTING : 수집 시작
    COLLECTING --> PROCESSING : sparse checkout + commit_sha 기록
    PROCESSING --> EMBEDDING : 전처리·섹션분리·청킹 완료
    EMBEDDING --> VALIDATING : 컬렉션 저장 완료

    RESTORING --> VALIDATING : tar 해제 + checksum 검증 통과
    RESTORING --> FAILED : checksum 불일치

    VALIDATING --> READY : 게이트 전 항목 통과 (≤10분)
    VALIDATING --> FAILED : 게이트 실패 · VALIDATION_TIMEOUT

    READY --> ACTIVE : make activate-index\n[단일 트랜잭션 INV-01]

    ACTIVE --> SUPERSEDED : 다음 run ACTIVE 전환
    SUPERSEDED --> ACTIVE : make rollback-index\n(직전 1개만)
    SUPERSEDED --> PURGED : 새 SUPERSEDED 발생 시\n(직전 1개 초과분)

    COLLECTING --> FAILED : GitHub API 오류·타임아웃
    PROCESSING --> FAILED : 전처리 오류
    EMBEDDING --> FAILED : 임베딩 실패 (재시도 포함)

    FAILED --> PURGED : 24시간 경과\n[Python APScheduler]

    PURGED --> [*]
```

> **INV-01:** source_key별 ACTIVE ingest_run 정확히 1개. READY→ACTIVE 전환은 단일 트랜잭션.
> **INV-04:** `chunk_id = SHA-256(source_key, commit_sha, file_path, heading_path, chunk_index, chunk_strategy, chunk_params_hash)[:32]` — 동일 SHA 재수집 시 동일 chunk_id 집합.

---

## 부록

### A. 서비스 간 종단 흐름

| 흐름 | 이어 붙일 절 | 상태 |
| --- | --- | --- |
| 단일 질문 전체 (이용량 확인 → 스트리밍 → 저장) | 4.1 → 5.1 | |
| 비교 질문 전체 (이용량 2회 차감 → 병렬 검색 → JSON 응답) | 4.1 → 5.2 | |
| 토큰 회전 → 재사용 탐지 전파 | 2.1 → 2.2 → 2.3 | |
| 인덱스 수집 → 활성화 → 기존 인덱스 교체 | 6.1 → 6.2 | |
| 게스트 세션 발급 → 한도 소진 → 환불 → 만료 | 3.1 | |

---

| 버전 | 내용 |
| --- | --- |
| v0.3 | §5.2 compare 엔드포인트·요청바디 수정, §6.2 INV-01 source_key 수정 |

---

end.
