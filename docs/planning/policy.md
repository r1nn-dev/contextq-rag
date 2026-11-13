# 서비스 정책 및 상태 정의

> 최종 수정일: 2026-11-06

---

## 1. 회원·인증 정책

인증은 "무상태 Access + 상태 저장 Refresh" 조합으로 확정한다. 탈취 시 노출 창을 30분으로 제한하면서, 로그아웃·재사용 탐지는 서버 상태로 강제하기 위함이다.

### 1.1 계정

| 항목 | 정책 |
| --- | --- |
| 식별자 | 이메일. 앞뒤 공백 제거 + 소문자 정규화 후 UNIQUE. 최대 254자, 형식 검사는 `@` 1개·도메인에 `.` 포함 수준(RFC 전체 검증은 하지 않음) |
| 이메일 인증 | 없음 (MVP 간소화). 따라서 비밀번호 재설정 기능도 제공하지 않음(P3) |
| 비밀번호 | 8~64자, 영문·숫자 각 1자 이상. 이메일과 동일한 문자열 금지 |
| 해시 | BCrypt cost 10. t3.small에서 로그인 1건 해시 지연 ≤ 200ms 목표(확정, W5는 기록용). cost 12는 CPU 크레딧 소모 대비 이득이 없다고 판단 |
| 표시 이름 | 별도 닉네임 없음. UI는 이메일 `@` 앞부분을 표시 |
| 역할 | `ROLE_USER`(가입 기본), `ROLE_ADMIN`. 역할은 계정당 1개 |
| 관리자 생성 | 가입 API로 생성 불가. 배포 시 환경 변수(`ADMIN_EMAIL`, `ADMIN_PASSWORD_BCRYPT`)로 1회 시드. 이미 존재하면 건너뜀 |
| 역할 변경 반영 | DB 변경 즉시 Refresh에는 반영, 기존 Access Token의 `role` 클레임은 만료(최대 30분)까지 유효. 무상태 검증의 트레이드오프로 명시 |
| 탈퇴·비밀번호 변경·소셜 로그인 | 범위 외 (기획서 5.5) |

### 1.2 로그인·토큰

| 항목 | 정책 |
| --- | --- |
| 로그인 실패 응답 | 계정 존재 여부와 무관하게 동일 메시지·동일 코드 `AUTH_INVALID_CREDENTIALS`(401). 미존재 계정도 더미 BCrypt 비교를 수행해 응답 시간 차이 제거 |
| 계정 잠금 | 동일 계정 15분 내 5회 실패 → 15분 잠금(`AUTH_LOCKED`, 429, `Retry-After` 포함). 성공 시 실패 카운트 초기화 |
| Access Token | JWT HS256, 30분. 클레임 `sub`(user_id), `role`, `iat`, `exp`, `jti`. 응답 본문으로 전달, 클라이언트는 **메모리에만 보관**(localStorage 금지, XSS 노출 차단). `Authorization: Bearer` 로 전송 |
| 서명 키 | 환경 변수 `JWT_SECRET`(32바이트 이상). 키 교체 시 기존 Access 전부 무효(재로그인 유도)를 감수 |
| 시계 오차 허용 | 30초 |
| Refresh Token | 256비트 불투명 난수(Base64URL). DB에는 **SHA-256 해시만 저장**. 쿠키 `devdocs_rt`: `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth` |
| 토큰 패밀리 | 로그인 1회 = 패밀리 1개. 패밀리 `expires_at = 로그인 시각 + 7일`(절대 만료). 회전해도 연장되지 않음 → 최대 7일마다 재로그인 |
| 회전(rotation) | `POST /api/v1/auth/refresh` 마다 새 Refresh 발급, 직전 토큰은 `USED`. 패밀리당 `ACTIVE` 토큰은 항상 최대 1개 |
| 재사용 탐지 | `USED` 토큰이 유예 시간(5초) **이후** 다시 제출되면 탈취로 간주 → 패밀리 전체 `REVOKED`, `AUTH_REFRESH_REUSED`(401), 쿠키 삭제 |
| 동시 갱신 경합 | 다중 탭이 동시에 refresh하는 경우를 위해, 회전 후 5초 이내 직전 토큰 재제출은 재사용으로 보지 않고 `AUTH_REFRESH_CONFLICT`(409) 반환. 이 시점 브라우저 쿠키는 이미 새 토큰이므로 클라이언트는 1회 재시도. 클라이언트는 탭 내 refresh를 단일 Promise로 직렬화(single-flight) |
| 로그아웃 | 현재 패밀리 `REVOKED` + 쿠키 `Max-Age=0`. 이미 발급된 Access는 만료까지 유효(최대 30분) — 트레이드오프로 명시 |
| 동시 로그인 | 기기·탭 수 제한 없음(패밀리 여러 개 허용). 사용자당 `ACTIVE` 패밀리 최대 10개, 초과 시 가장 오래된 패밀리 `REVOKED` |

### 1.3 비로그인(게스트) 이용

| 항목 | 정책 |
| --- | --- |
| 식별 | 서버 발급 쿠키 `devdocs_sid`(128비트 난수, `HttpOnly; Secure; SameSite=Strict; Path=/api`). DB `app.guest_sessions`에 해시로 저장 |
| 발급 시점 | 게스트가 최초 질문 API를 호출할 때(페이지 진입만으로는 발급하지 않음 → 크롤러·새로고침에 의한 레코드 증가 방지) |
| 한도 | 세션당 질문 5회. 서버 TTL 24시간(최초 발급 기준 절대 만료, 사용해도 연장 없음) |
| 차감 규칙 | 요청 검증 통과 시 원자적 차감: `UPDATE … SET used = used + 1 WHERE sid_hash = ? AND used < 5 AND expires_at > now()`. 영향 행 0이면 `GUEST_QUOTA_EXCEEDED`(429) |
| 환불 규칙 | `meta` 이벤트 전송 **이전**에 서버 측 원인(ai-server 연결 실패·첫 이벤트 타임아웃·5xx)으로 실패하면 1회 환불. 클라이언트 중단·NO_CONTEXT·`meta` 이후 실패는 환불하지 않음 |
| 이용 가능 모드 | **단일 모드만**. 비교 모드는 로그인 필요(`GUEST_MODE_NOT_ALLOWED`, 403). 근거: 비교 1회가 검색 2회 + 긴 JSON 생성으로 단일 대비 비용·지연 2배 이상이며, 로그인 전환 유인이 됨 |
| 이력 | 서버 저장 없음. 대화는 브라우저 메모리에만 존재(새로고침 시 소실) |
| 로그인 시 이관 | 하지 않음. 로그인 후에는 새 대화로 시작. 이관 기능은 서버 저장이 없어 원본 신뢰성(출처·스냅샷)을 보장할 수 없으므로 제외 |
| 쿠키 삭제 우회 | 완전 차단 불가를 전제로, IP당 신규 게스트 세션 발급을 1시간 30개로 제한(`GUEST_SESSION_LIMIT`, 429). 30개는 전시회장 공용 Wi-Fi(단일 NAT IP) 환경을 고려한 값 |
| 로그인 사용자 | 게스트 쿠키가 있어도 유효한 Access가 있으면 로그인 사용자로 처리, 게스트 카운트 차감 없음 |

---

## 2. 시간·TTL 정책

- 모든 타임아웃은 "안쪽 계층이 바깥 계층보다 먼저 끝난다"는 규칙으로 정렬한다.
- `OpenAI < ai-server < backend < nginx` 순서가 깨지면 바깥 계층이 원인을 모른 채 연결을 끊게 된다.

### 2.1 TTL 표

| 항목 | 값 | 의미 | 근거 |
| --- | --- | --- | --- |
| Access Token | 30분 | JWT 유효 시간 | 탈취 시 노출 창 제한과 refresh 빈도(시간당 2회)의 균형 |
| Refresh 패밀리 절대 만료 | 7일 | 로그인 후 재로그인까지 최대 기간 | 회전으로 무한 연장되는 세션 차단. 학습 주기(주 단위)에 맞춤 |
| Refresh 회전 경합 유예 | 5초 | 직전 토큰 재제출을 재사용으로 보지 않는 창 | 다중 탭 동시 갱신 오탐 방지. 5초 초과는 탈취 탐지 약화 |
| USED·REVOKED 토큰 레코드 | 패밀리 만료 + 1일 후 삭제 | 재사용 탐지 근거 보관 | 패밀리 만료 전 삭제하면 재사용을 "모르는 토큰"으로 처리하게 됨 |
| JWT 시계 오차 허용 | 30초 | exp·iat 비교 여유 | 컨테이너 간 시계 편차 흡수 |
| 로그인 실패 윈도우 / 잠금 | 15분 / 15분 | 5회 실패 판정 구간과 잠금 시간 | 무차별 대입 속도 제한. 정상 사용자 불편 최소화 |
| 게스트 세션(`devdocs_sid`) | 24시간 (절대) | 5회 한도가 유지되는 기간 | 기획서 6.3. 사용 시 연장하면 한도가 사실상 무한 |
| 게스트 세션 레코드 | 만료 + 24시간 후 삭제 | IP 발급 한도 계산용 보관 | 일 1회 정리 배치 |
| WebClient 연결 타임아웃 | 3초 | backend → ai-server TCP 연결 | 내부망이므로 3초 초과는 장애로 판정 |
| 첫 이벤트(`meta`) 타임아웃 | 15초 | 요청 후 `meta` 도착까지 | 재작성(≤3초) + 임베딩(≤5초) + 검색(≤0.5초)의 최악 합에 여유 |
| 유휴 타임아웃 | 30초 | 이벤트 간 최대 간격 | 하트비트(10초)가 3회 연속 누락되면 끊긴 것으로 판정 |
| SSE 하트비트 | 10초 | ai-server가 보내는 `: ping` 주석 | `meta` 후 첫 토큰 대기 구간에서 유휴 판정 방지 |
| 단일 스트림 최대 시간 | 120초 | 한 응답의 절대 상한 | 연결 누수 차단. `max_tokens=1024` 생성 시간(약 30초)의 4배 |
| 비교 모드 전체 타임아웃 | 30초 | 요청~JSON 응답 | 목표 p50 12초의 2.5배. 초과 시 `UPSTREAM_TIMEOUT` |
| OpenAI 임베딩 호출 | 5초, 재시도 1회 | 질의 임베딩 | 멱등 호출이므로 재시도 허용 |
| OpenAI 생성 첫 토큰 | 10초, 재시도 없음 | chat completion 스트림 시작 | 스트림은 재시도 시 중복·비용 발생. `meta` 15초 이내에 실패 확정 |
| 질의 재작성 호출 | 3초 | 멀티턴 재작성 LLM 호출 | 초과 시 원 질문으로 폴백(실패 아님) |
| nginx `proxy_read_timeout` | 150초 | nginx가 backend 응답을 기다리는 한도 | 반드시 스트림 최대 시간(120초)보다 커야 함 |
| STREAMING 고착 판정 | 150초 | 스위퍼가 `FAILED(STALE)`로 전환하는 기준 | 스트림 최대 시간 + 30초. 프로세스 비정상 종료 대비 |
| 스위퍼 주기 | 60초 | STREAMING 고착 정리 배치 | backend `@Scheduled` |
| 메타 API 캐시 | 60초 | `GET /meta/sources` 응답 캐시 | 인덱스 활성화 시 캐시 즉시 무효화 |
| ai-server 활성 인덱스 포인터 캐시 | 30초 (+ reload 즉시 반영) | ai-server가 활성 run을 재조회하는 주기 | reload 호출 실패 시 안전망 |
| 인덱스 VALIDATING 제한 시간 | 10분 | 검증 단계 최대 시간 | 초과 시 `FAILED(VALIDATION_TIMEOUT)`, 기존 인덱스 유지 |
| FAILED 컬렉션 | 24시간 후 삭제 | 실패 인덱스 디버깅용 보관 | 디스크(20GiB) 보호 |
| SUPERSEDED 인덱스 | 직전 1개만 보관 | 롤백 대상 | 시간이 아니라 개수 기준 (기획서 6.3) |
| 대화 이력 | 영구 | 대화·메시지·출처 | 졸업작품 범위 삭제 정책 없음 |
| Postgres 백업 | 일 1회 03:00 KST, 7일 보관 | S3 `pg_dump` | RPO 24시간 |
| 컨테이너 로그 | json-file 10MB × 3개 | 서비스별 로그 회전 | 디스크 보호 |

### 2.2 불변식

```
[인덱스]
INV-01 (framework, version)마다 ACTIVE ingest_run은 정확히 1개다. 서비스 개시 후 0개 상태는 존재하지 않는다.
       교체는 포인터 1행 UPDATE로만 일어난다(원자적 전환).
INV-02 검색은 ACTIVE run의 컬렉션에서만 수행한다. 검색 결과 청크의 version·ingest_run_id 메타데이터가
       요청과 다르면 해당 청크를 폐기하고 ERROR 로그를 남긴다(컬렉션 분리에 대한 방어적 2차 검증).
INV-03 청크의 embedding_model은 질의 임베딩 모델과 같다. 다르면 검색을 거부한다(EMBEDDING_MODEL_MISMATCH).
INV-04 동일 commit_sha·동일 청킹 파라미터로 재수집하면 동일 chunk_id 집합이 생성된다.
INV-05 permalink는 커밋 SHA를 포함한 URL만 허용한다. 브랜치명(main, v0.3) URL은 저장 단계에서 거부한다.

[스트림]
INV-06 한 응답의 이벤트 순서는 meta → token* → (done | error)이며, meta와 종결 이벤트는 각각 정확히 1회다.
INV-07 NO_CONTEXT(reason=LOW_SIMILARITY)는 생성 LLM을 호출하지 않는다. (멀티턴 재작성 LLM 호출은 발생할 수 있다)
INV-08 답변 본문의 인용 번호 [n]은 meta.sources의 rank 범위 안에 있어야 한다. 범위 밖 번호는 done.invalid_citations에 기록된다.
INV-09 HTTP 200으로 스트림이 시작된 이후의 오류는 HTTP 상태가 아니라 error 이벤트로만 전달한다.

[대화·메시지]
INV-10 대화의 source_key(비교 모드는 source_key_a·source_key_b)·mode는 생성 후 변경되지 않는다.
INV-11 한 대화에서 진행 중(PENDING·STREAMING·PROCESSING)인 assistant 메시지는 최대 1개다.
INV-12 종결 상태(COMPLETED·PARTIAL·NO_CONTEXT·FAILED)인 메시지는 다른 상태로 전이하지 않는다.
INV-13 assistant 메시지는 생성 시점의 ingest_run_id·commit_sha·prompt_version·model을 스냅샷으로 저장한다.
       출처도 청크 참조가 아닌 값(heading_path·permalink·similarity)으로 복사 저장한다 → 인덱스 교체·삭제 후에도 이력이 유지된다.
INV-14 대화·메시지는 소유자만 조회한다. 타인 리소스 요청은 존재 여부와 무관하게 404다.

[인증·이용량]
INV-15 Refresh 패밀리당 ACTIVE 토큰은 최대 1개다.
INV-16 게스트 세션의 used_count는 0 이상 5 이하다.
INV-17 prod 프로필에서는 수집·임베딩 경로와 mock LLM이 비활성이며, 활성화 설정이 감지되면 기동을 실패시킨다(fail-fast).
```

### 2.3 사용자 이탈 구간별 복구

| 구간 | 복구 기준 | 복구 방법 | 재진입 조건 |
| --- | --- | --- | --- |
| 질문 전송 직후, `meta` 도착 전 (탭 닫기·네트워크 단절) | 메시지 `FAILED(CLIENT_ABORTED)`. 업스트림 취소 전파 | backend가 클라이언트 취소를 감지해 WebClient 구독 해제 → ai-server가 OpenAI 호출 중단. 게스트는 환불하지 않음(클라이언트 원인) | 동일 질문 재전송. 로그인 사용자는 이력에 "전송 실패" 표시 |
| 토큰 스트리밍 중 이탈 | 수신 토큰이 1개 이상이면 `PARTIAL(CLIENT_ABORTED)`, 0개면 `FAILED` | 취소 전파로 OpenAI 스트림 중단(비용 절감). 그때까지 누적된 본문과 출처를 저장 | 이력 상세에서 부분 답변 + "중단됨" 배지 + "다시 생성" 버튼(새 메시지로 생성, 기존 메시지 유지) |
| 서버 측 유휴 타임아웃 (30초) | 토큰 ≥ 1이면 `PARTIAL(UPSTREAM_IDLE_TIMEOUT)`, 아니면 `FAILED` | 클라이언트에 `error` 이벤트(`partial: true/false`) 전송 후 종료 | 화면에 부분 답변 유지 + 재질문 버튼. 자동 재연결은 하지 않음(기획서 결정 5) |
| `max_tokens` 도달 | `PARTIAL(LENGTH)` | done 이벤트 `finish_reason=length` | "답변이 길어 잘렸습니다" 안내 + "이어서 설명해줘" 후속 질문 유도 |
| 스트림 완료 후 DB 저장 실패 | 사용자 응답은 이미 전달됨. 메시지는 STREAMING으로 남음 | 저장 1회 재시도 → 실패 시 `request_id`와 함께 ERROR 로그. 스위퍼가 150초 후 `FAILED(PERSIST_ERROR)`로 전환 | 이력에 "저장 실패" 표시. 재질문 가능 |
| 비교 모드 대기 중 이탈 (로그인) | 취소를 전파하지 않고 끝까지 처리 | 완료 시 `COMPLETED`로 저장 | 이력에서 결과 확인 가능. 단일 호출이라 중단해도 절감 비용이 작고, 결과 보존 가치가 더 큼 |
| Access 만료 상태에서 요청 | 스트림은 시작 시점에만 인증 검증. 진행 중 만료는 영향 없음 | 다음 요청이 401 `AUTH_TOKEN_EXPIRED` → 클라이언트 silent refresh → 원 요청 1회 재시도 | refresh 성공 |
| Refresh 만료(7일)·재사용 탐지·로그아웃 | 세션 종료 | 로그인 화면으로 이동. 입력창의 작성 중 질문은 sessionStorage에 임시 저장 후 로그인 뒤 복원 | 재로그인 |
| 게스트 5회 소진 | `GUEST_QUOTA_EXCEEDED` | 로그인 유도 모달. 브라우저 메모리의 기존 대화는 읽기만 가능 | 로그인(대화 이관 없음) 또는 24시간 후 새 세션 |
| 게스트 새로고침·탭 닫기 | 대화 소실(서버 저장 없음), 카운트는 유지 | 복구 불가를 UI에 사전 고지("로그인하면 대화가 저장됩니다") | 동일 `devdocs_sid`로 남은 횟수 이어서 사용 |
| 인덱스 교체 중 질문 | 진행 중 요청은 시작 시 확정한 run으로 끝까지 처리 | SUPERSEDED 컬렉션은 즉시 삭제하지 않으므로 in-flight 요청 실패 없음 | 다음 질문부터 새 ACTIVE run 사용. 같은 대화에 스냅샷이 섞이면 메시지별 커밋 SHA 표시로 구분 |
| ai-server 다운·재시작 | 연결 3초 실패 → `AI_UNAVAILABLE`(503), 메시지 `FAILED` | 게스트는 1회 환불. Docker `restart: unless-stopped` | `/internal/v1/health`가 정상으로 돌아온 뒤 재질문 |
| 이어서 질문하려는 대화의 버전이 비활성화됨 | 대화는 읽기 전용 | 이어서 질문 시 `SOURCE_UNAVAILABLE`(409) | 해당 버전 재활성화 또는 새 대화 |
| 대화 메시지 상한(100개) 도달 | 대화는 읽기 전용 | `CONVERSATION_FULL`(409) + "새 대화 시작" 버튼 | 새 대화(버전·모드 기본값으로 기존 대화 설정을 제안) |

---

## 3. 소스·버전 정책

버전 목록은 코드가 아니라 `ai.sources` 카탈로그 테이블이 소유한다. UI·backend·ai-server 어디에도 버전 문자열을 하드코딩하지 않는다(UI-01).

### 3.1 소스 카탈로그

| source_key | framework | version_label | 저장소 · ref · 경로 | 포맷 | Adapter |
| --- | --- | --- | --- | --- | --- |
| `langchain_v03` | langchain | v0.3 | `langchain-ai/langchain` · `v0.3` · `docs/docs/` | Docusaurus (.mdx, .md, .ipynb) | `DocusaurusAdapter` |
| `langchain_v1x` | langchain | v1.x | `langchain-ai/docs` · `main` · `src/oss/` | Mintlify (.mdx + 스니펫) | `MintlifyAdapter` |

### 3.2 정책

| 항목 | 정책 |
| --- | --- |
| 버전 의미 | `v1.x`는 "수집 커밋 시점의 main 문서"를 뜻하며 특정 마이너(1.0, 1.1)를 보장하지 않는다. UI는 버전명 옆에 커밋 SHA 앞 7자리와 수집일을 항상 함께 표시한다 |
| 수집 언어 | Python 문서만. JS/TS 전용 페이지·코드 블록은 제외(1.x `:::js` 블록 제거) |
| 포함 범위 | 개념·튜토리얼·how-to·마이그레이션 가이드(`migrate/langchain-v1` 포함 필수) |
| 제외 범위 | `integrations/**`(수백 개 제공자 페이지, 버전 단절 학습과 무관하고 레이블링 비용 과다), `langgraph` 패키지 문서(별도 버전 체계, v0.3 ↔ v1.x 비교 프레이밍과 무관 — 관련 질문은 NO_CONTEXT 처리), 자동 생성 API Reference, LangSmith 문서, 블로그·릴리스 노트. 최종 경로 목록은 `docs/data-sources.md`에 커밋 SHA와 함께 고정. W1에서 Q-shared 초안에 integrations·langgraph가 gold인 질문이 있으면 해당 질문을 교체(제외 정책 변경 아님) |
| 활성 조건 | `enabled = true` AND ACTIVE run 존재. 둘 중 하나라도 거짓이면 메타 API에서 제외되고 신규 질문 불가 |
| 비교 쌍 | `ai.compare_pairs`에 정의된 쌍만 허용. 현재 `(langchain_v03, langchain_v1x)` 1개. 순서는 항상 구버전 = A, 신버전 = B |
| `compare_enabled` | 쌍의 양쪽 소스가 모두 활성 조건을 만족할 때만 true |
| 소스 비활성화 | `enabled = false`로 전환해도 기존 대화·이력은 유지되고 읽기 전용이 된다(2.3절) |
| 신규 프레임워크 추가 | Adapter 구현 + 카탈로그 행 추가만으로 가능해야 한다. 졸업작품 범위에서는 추가하지 않으며, 확장 경로만 보고서에 기술(기획서 5.5) |

### 3.3 메타 API 응답 계약 (`GET /api/v1/meta/sources`)

```json
{
  "frameworks": [{
    "key": "langchain",
    "display_name": "LangChain",
    "versions": [
      { "source_key": "langchain_v03", "label": "v0.3",
        "active_run": { "ingest_run_id": 12, "commit_sha": "a1b2c3d", "ingested_at": "2026-10-05", "chunk_count": 4210 } },
      { "source_key": "langchain_v1x", "label": "v1.x",
        "active_run": { "ingest_run_id": 13, "commit_sha": "e4f5a6b", "ingested_at": "2026-10-05", "chunk_count": 3380 } }
    ],
    "compare_pairs": [{ "a": "langchain_v03", "b": "langchain_v1x" }],
    "compare_enabled": true
  }],
  "guest": { "remaining": 3, "limit": 5 }
}
```

`guest`는 게스트 요청에만 포함한다. 로그인 사용자는 `guest: null`이다. 값은 예시다.

---

## 4. 인덱스 정책

인덱스는 "버전 관리되는 빌드 산출물"로 다룬다. 로컬에서 빌드·검증하고, 운영은 검증된 스냅샷의 복원·활성화만 수행한다(기획서 결정 4).

### 4.1 식별과 결정성

| 항목 | 정책 |
| --- | --- |
| `ingest_run_id` | 단조 증가 정수. 로컬 빌드 시 발급되며 스냅샷 manifest에 포함되어 운영에 그대로 복원된다 |
| 컬렉션 이름 | `{source_key}_run{ingest_run_id}` (예: `langchain_v03_run12`). run과 컬렉션은 1:1 |
| `chunk_id` | `sha256(source_key, commit_sha, file_path, heading_path, chunk_index, chunk_strategy, chunk_params_hash)` 앞 32자. 같은 입력이면 같은 ID(INV-04, RAG-02) |
| 청킹 파라미터 | `chunk_params`(JSON)와 그 해시를 run에 기록. E2 확정 전까지 전략 A·B·C는 서로 다른 run으로 생성 |
| 거리 함수 | cosine 고정(`hnsw:space = cosine`). similarity = 1 − distance |

### 4.2 청크 메타데이터 필수 필드

누락 필드가 1개라도 있으면 VALIDATING 실패다.

| 필드 | 예시 | 용도 |
| --- | --- | --- |
| `chunk_id` | `9f2c…` | 결정적 식별자 |
| `source_key` / `framework` / `version` | `langchain_v1x` / `langchain` / `v1.x` | 격리 2차 검증(INV-02) |
| `ingest_run_id` / `commit_sha` | `13` / `e4f5a6b…`(40자) | 스냅샷 추적 |
| `file_path` | `src/oss/langchain/agents.mdx` | permalink 생성 |
| `heading_path` | `Agents > Tools > Defining tools` | 출처 카드 표시 |
| `line_start` / `line_end` | `120` / `168` | 라인 앵커 permalink |
| `permalink` | `https://github.com/…/blob/{sha}/…?plain=1#L120-L168` | 불변 출처 |
| `site_url` | `https://docs.langchain.com/…` | 보조 링크(불변 보장 없음) |
| `doc_type` | `mdx` / `md` / `ipynb` | 전처리 추적 |
| `chunk_strategy` / `chunk_params_hash` | `C` / `a1b2` | 실험 조건 추적 |
| `embedding_model` | `text-embedding-3-small` | INV-03 |
| `token_count` / `has_code` | `312` / `true` | 컨텍스트 예산, 정성 분석 |

### 4.3 전처리 규칙

| 대상 | 규칙 | 자동 검사 |
| --- | --- | --- |
| 공통 | frontmatter 제거, `title`은 heading_path 최상위로 사용 | frontmatter 잔존 0건 |
| 1.x 조건부 블록 | `:::python` 내용은 보존·마커만 제거, `:::js` 블록은 내용까지 제거 | `:::js` 잔존 0건(RAG-03) |
| 1.x 스니펫 | `import X from '/snippets/…'` + `<X />`를 스니펫 본문으로 인라인 확장. 파일이 없으면 태그 제거 + `missing_snippets.csv` 기록 | 누락 목록 산출 |
| JSX 태그 | `<Tabs>`, `<Card>` 등 태그는 제거하고 텍스트 자식만 보존. 코드 펜스 내부는 절대 변경하지 않음 | 코드 펜스 내부 diff 0 |
| 노트북(.ipynb) | markdown 셀 + code 셀을 셀 순서대로 직렬화, 출력 셀 제거, code 셀은 ```python 펜스로 감쌈 | 출력 셀 잔존 0건 |
| 코드 펜스 | 어떤 전략에서도 펜스 중간 분할 금지(전략 C는 원자 단위, A·B는 사후 검사로 분할 건수 보고) | E2 보고 항목 |
| 빈 섹션 | 전처리 후 본문 50자 미만 섹션은 청크를 만들지 않고 상위 섹션에 병합 | 50자 미만 청크 0건 |

### 4.4 검증(VALIDATING) 게이트

모든 항목을 통과해야 READY가 된다. 하나라도 실패하면 FAILED이며 기존 ACTIVE는 그대로 유지된다(RAG-10).

| 검사 | 통과 기준 |
| --- | --- |
| 청크 수 | 0 초과. 직전 ACTIVE 대비 ±30% 이내(초과 시 `--accept-drift` 플래그로만 통과, 사유를 run에 기록) |
| 필수 메타데이터 | 누락 0건 (4.2) |
| 전처리 잔존물 | 4.3 자동 검사 전부 0건 |
| permalink 유효성 | 파일 단위 중복 제거 후 전수 HTTP 200 (GitHub 토큰 사용, 초당 5건 제한) |
| 임베딩 차원·모델 | 전 청크 동일 모델·동일 차원(1536) |
| 스모크 질문 | 버전당 5문항: 기대 파일이 Top-5 안에 있고 top-1 similarity ≥ τ. 5문항 중 5문항 통과 |
| 스냅샷 복원 검증 | 복원 후 청크 수·checksum·스모크 결과가 manifest와 일치(RAG-11) |

### 4.5 활성화·롤백·스냅샷

| 항목 | 정책 |
| --- | --- |
| 활성화 | `ai.index_pointers(source_key → active_run_id)` 1행을 트랜잭션으로 UPDATE. 기존 ACTIVE → SUPERSEDED, 대상 READY → ACTIVE를 같은 트랜잭션에서 처리 |
| 반영 | 활성화 CLI가 `POST /internal/v1/index/reload` 호출. 실패해도 30초 포인터 캐시 만료로 반영 |
| 롤백 | `make rollback-index SOURCE=…` : 직전 SUPERSEDED를 다시 ACTIVE로, 현재 ACTIVE는 SUPERSEDED로. 롤백 대상은 1세대뿐 |
| 정리 | 새 SUPERSEDED가 생기면 그 이전 SUPERSEDED는 PURGED(컬렉션 삭제). FAILED는 24시간 후 PURGED |
| 스냅샷 구성 | `snapshot-{source_key}-run{id}.tar.gz` = Chroma 컬렉션 디렉터리 + `manifest.json`(run id, commit_sha, 청킹 파라미터, 임베딩 모델, 청크 수, sha256 checksum, 검증 리포트) |
| 스냅샷 보관 | S3 `s3://…/index-snapshots/`에 run별 보관. 최종 발표(12/10)까지 삭제하지 않음 |
| 운영 수집 금지 | prod 프로필에서 수집·임베딩 명령과 재수집 API는 빈(bean) 자체를 등록하지 않음. 호출 시 `FORBIDDEN_IN_PROFILE`(403) |

---

## 5. 검색·생성 정책

검색 단계는 버전 혼입을 "차단"하고, 생성 단계는 "측정·완화"한다(기획서 8.5 예상 질문 3). 이 구분이 NO_CONTEXT의 두 가지 사유로 그대로 드러나도록 설계한다.

### 5.1 입력 검증

| 항목 | 정책 |
| --- | --- |
| 질문 길이 | trim 후 1~1,000자. 위반 시 `INVALID_REQUEST`(400) |
| 질문 언어 | 한국어·영어 모두 허용. 답변은 한국어 고정, API명·코드·에러 메시지는 원문 유지 |
| 필수 파라미터 | 신규 대화: `source_key`(단일) 또는 `source_key_a`·`source_key_b`(비교). 기존 대화: `conversation_id`만 — 버전 파라미터가 함께 오면 무시하지 않고 대화 설정과 다를 때 400 |
| 게스트 이력 파라미터 | 게스트만 `history`(최근 3턴, 메시지당 최대 2,000자) 전송. 서버가 개수·길이를 재검증·절단 |
| 로그인 사용자 이력 | 서버 DB 기준. 클라이언트가 보낸 `history`는 무시(조작된 맥락 주입 차단) |

### 5.2 질의 재작성(멀티턴)

| 항목 | 정책 |
| --- | --- |
| 적용 대상 | 대화의 2번째 이후 질문. 첫 질문은 원문 그대로 검색 |
| 참조 범위 | 최근 3턴(6메시지). 이전 assistant 본문은 앞 500자만 사용(재작성 토큰 제어) |
| 제외 메시지 | FAILED assistant 메시지, NO_CONTEXT 고정 안내문. 해당 턴의 user 질문은 포함 |
| 출력 | 단독으로 검색 가능한 질의 1개, 200자 이하, 원 질문 언어 유지 |
| 실패 처리 | 3초 초과·빈 출력·200자 초과 시 원 질문으로 폴백. `rewrite_status = OK / FALLBACK / SKIPPED` 기록 |
| 투명성 | `rewritten_query`를 `meta` 이벤트와 DB에 기록, UI는 접힌 상태로 "검색에 사용된 질의" 표시 |

### 5.3 검색

| 항목 | 정책 |
| --- | --- |
| 대상 | 요청 source의 ACTIVE run 컬렉션 1개만 직접 지정(1차 격리) + 결과 메타데이터 재검증(INV-02, 2차) |
| Top-K | 초기값 5. E2 결정 규칙으로 확정(K ∈ {3, 5, 8}) |
| 임계값 τ | 미결정(W2 E1 부속 실험). 확정 전 개발용 임시값 0.30 |
| 컨텍스트 채택 | Top-K 중 similarity ≥ τ 인 청크만 컨텍스트에 넣음 |
| 컨텍스트 예산 | 최대 3,000 토큰. 초과 시 낮은 rank부터 제외(청크 중간 절단 금지) |
| 지연 기록 | `rewrite_ms`, `embed_ms`, `retrieve_ms`를 done 이벤트와 DB에 기록 |

### 5.4 NO_CONTEXT 판정

| reason | 조건 | 생성 LLM 호출 | 이벤트 흐름 |
| --- | --- | --- | --- |
| `LOW_SIMILARITY` | top-1 similarity < τ | 호출 안 함 (INV-07) | `meta`(sources: [], no_context: true) → `done`(status: NO_CONTEXT) |
| `LLM_ABSTAIN` | 컨텍스트는 통과했으나 모델이 근거 부족을 선언 | 호출함 | `meta`(sources 포함) → `done`(status: NO_CONTEXT) |
- `LLM_ABSTAIN` 판정: 프롬프트가 근거 부족 시 첫 출력을 `[[NO_ANSWER]]`로 시작하도록 지시한다. ai-server는 첫 16자를 버퍼링해 sentinel이면 토큰을 내보내지 않고 NO_CONTEXT로 종결한다.
- 기획서의 "Q-oos 10건 중 8건 이상 LLM 미호출" 지표는 `LOW_SIMILARITY`만 집계한다. `LLM_ABSTAIN`은 L3 완화 효과로 별도 집계한다.
- 고정 안내문: "선택한 버전({label}, {commit_sha_7}) 문서에서 근거를 찾을 수 없습니다." + 다른 버전으로 질문하기 버튼(비교 가능한 경우).

### 5.5 생성(단일 모드)

| 항목 | 정책 |
| --- | --- |
| 모델 | `LLM_MODEL` 환경 변수, 기본 `gpt-4o-mini`. 메시지에 실제 모델명 기록 |
| 파라미터 | temperature 0, `max_tokens` 1,024 |
| 프롬프트 규칙 | ① 컨텍스트 밖 지식으로 API·코드를 만들지 않는다 ② 주장마다 [n] 인용 ③ 선택 버전을 답변 첫 줄에 명시 ④ 코드 예시는 컨텍스트 코드에 근거 ⑤ 근거 부족 시 sentinel |
| 프롬프트 버전 | `prompts/` 디렉터리의 파일명 = `prompt_version`(예: `single_v3`). 변경은 PR + 동일 질문셋 비교 결과 첨부 |
| 인용 검증 | 스트림 종료 시 본문의 [n]을 파싱해 범위 밖 번호를 `done.invalid_citations`로 전송. UI는 해당 번호를 비활성 렌더 |

### 5.6 생성(비교 모드)

| 항목 | 정책 |
| --- | --- |
| 검색 | A·B 각각 5.3 규칙으로 독립 검색(K는 각각 적용) |
| 한쪽 근거 없음 | 해당 측 top-1 < τ 이면 그 측은 "해당 버전 문서에서 근거 없음"으로 고정하고 다른 측만 요약. 변경점 목록은 생성하지 않음 |
| 양쪽 근거 없음 | NO_CONTEXT(`LOW_SIMILARITY`), 생성 LLM 미호출 |
| 인용 번호 체계 | A측 `A1…Ak`, B측 `B1…Bk`로 접두어를 분리해 버전 간 번호 혼동 차단 |
| 출력 | OpenAI Structured Outputs(JSON Schema) 사용, `max_tokens` 1,500 |
| 후처리 검증 | 존재하지 않는 인용 번호 제거. 변경점 항목에 A·B 인용이 모두 없으면 해당 항목 폐기("양쪽 근거 인용 필수") |
| 파싱 실패 | 1회 재시도 후에도 실패하면 `FAILED(COMPARE_PARSE_ERROR)` |
| 멀티턴 | 허용. 재작성 규칙(5.2)을 동일하게 적용하며 재작성 질의 1개로 양쪽을 검색 |

```json
{
  "version_a": { "summary": "…", "citations": ["A1", "A3"], "no_evidence": false },
  "version_b": { "summary": "…", "citations": ["B2"], "no_evidence": false },
  "changes": [
    { "aspect": "에이전트 생성 함수", "a": "…", "b": "…", "citations_a": ["A1"], "citations_b": ["B2"] }
  ]
}
```

### 5.7 Mock LLM 모드

| 항목 | 정책 |
| --- | --- |
| 허용 프로필 | `loadtest`, `local`만. `prod`에서 설정 감지 시 기동 실패(INV-17) |
| 동작 | 검색까지는 실제 수행, 생성만 대체. 고정 200토큰을 20ms 간격으로 방출(약 4초, 실측 생성 속도에 맞춰 조정) |
| 목적 | E6에서 OpenAI 비용·속도 변수를 제거하고 EC2 자원 한계만 측정 |

---

## 6. 대화·메시지 정책

대화는 "버전·모드가 고정된 학습 세션"이고, 메시지는 "어느 스냅샷·프롬프트로 만들어졌는지 재현 가능한 기록"이다. 이력이 실험 데이터로도 쓰일 수 있도록 메타데이터를 값으로 저장한다(INV-13).

### 6.1 대화

| 항목 | 정책 |
| --- | --- |
| 생성 | 별도 생성 API 없음. `conversation_id` 없이 첫 질문을 보내면 서버가 생성하고 `meta` 이벤트로 ID 반환 |
| 고정 속성 | `mode`(SINGLE/COMPARE), `source_key` 또는 `source_key_a`·`source_key_b` (INV-10) |
| 제목 | 첫 질문 앞 40자(줄바꿈 제거). LLM 요약 제목은 비용 대비 가치가 낮아 제외 |
| 메시지 상한 | 100개(50턴). 재작성은 최근 3턴만 쓰므로 품질 영향은 없고, 상세 조회 응답 크기를 제한하기 위함 |
| 동시 진행 | 대화당 진행 중 메시지 1개(INV-11). 위반 시 `CONVERSATION_BUSY`(409) |
| 정렬·목록 | `updated_at` 내림차순, 커서 기반 페이지네이션 20개. `updated_at`은 assistant 메시지가 종결될 때 갱신 |
| 목록 항목 | id, 제목, mode, 버전 라벨, 마지막 메시지 상태, 메시지 수, updated_at |
| 삭제 | 제공하지 않음(영구 보존, 기획서 6.3) |
| 권한 | 소유자만 조회·이어서 질문. 타인 요청은 404(INV-14). 관리자도 타인 대화 조회 API는 없음 |

### 6.2 메시지 저장 항목

| 구분 | 필드 |
| --- | --- |
| 공통 | `id`, `conversation_id`, `role`(USER/ASSISTANT), `content`, `created_at`, `request_id` |
| 상태 | `status`, `status_reason`(10장 참조), `finish_reason` |
| 검색 | `rewritten_query`, `rewrite_status`, `ingest_run_id`(비교 모드는 A·B 각각), `commit_sha`, `top1_similarity` |
| 출처 | `message_sources`: rank(또는 A1·B1 라벨), chunk_id, heading_path, permalink, site_url, similarity |
| 생성 | `model`, `prompt_version`, `prompt_tokens`, `completion_tokens`, `invalid_citations` |
| 지연 | `rewrite_ms`, `embed_ms`, `retrieve_ms`, `ttft_ms`, `total_ms` |
| 비교 모드 | `compare_result`(5.6 JSON, 후처리 검증 후 값) |

### 6.3 저장 시점

1. 요청 수락: USER 메시지 INSERT + ASSISTANT 메시지 `PENDING` INSERT (같은 트랜잭션). 이 시점에 INV-11 검사.
2. `meta` 수신: ASSISTANT → `STREAMING`, 출처·스냅샷 정보 저장.
3. 토큰 수신: backend 메모리 버퍼에 누적(토큰마다 DB 쓰기 금지).
4. 종결(`done`/`error`/클라이언트 취소): 누적 본문 + 사용량·지연과 함께 종결 상태로 UPDATE 1회.
5. 게스트: 1~4를 DB에 쓰지 않는다. 대신 이용량 집계용 `guest_usage_log`(sid_hash, status, tokens, 시각)만 기록.

---

## 7. 출처·인용 정책

- 주 출처는 커밋 SHA 고정 GitHub permalink이고, 문서 사이트 URL은 보조 링크다.
- 사이트 URL은 구조 개편 시 깨질 수 있어 자동 검증 100% 기준을 걸 수 없다(기획서 5.2.2).

| 항목 | 정책 |
| --- | --- |
| permalink 형식 (.md/.mdx) | `https://github.com/{owner}/{repo}/blob/{commit_sha}/{file_path}?plain=1#L{line_start}-L{line_end}` — `?plain=1`이 없으면 GitHub가 렌더링 뷰를 보여 라인 앵커가 동작하지 않음. W1 샘플 10개 확인에서 미작동 판정 시 폴백: `?plain=1`·`#L` 앵커를 제거한 파일 단위 permalink로 저장, 섹션 일치 인수 기준 자동으로 15건으로 조정 |
| permalink 형식 (.ipynb) | `https://github.com/{owner}/{repo}/blob/{commit_sha}/{file_path}` (파일 단위, 라인 앵커 없음) |
| site_url | v0.3: `python.langchain.com/v0.3/docs/…`, v1.x: `docs.langchain.com/oss/python/…`. 변환 규칙은 Adapter가 소유. 변환 불가 시 null |
| 출처 카드 표시 | rank 번호, heading_path, 파일명, similarity(소수 둘째 자리), "원문 보기(고정)" = permalink, "문서 사이트(현재)" = site_url |
| 스냅샷 표시 | 모든 답변 하단에 `v1.x · e4f5a6b · 2026-10-05 수집` 형식 |
| 동일 파일 중복 | 같은 파일의 청크가 여러 개면 카드는 청크별로 유지(인용 번호가 청크 단위이므로 병합하지 않음) |
| 자동 검증 | VALIDATING 게이트에서 전수 HTTP 200 (4.4). 운영 중에는 `make check-permalinks`로 최종 발표 전 1회 재검증 |
| 섹션 일치 수동 검증 | 무작위 20건: permalink 라인 범위 안에 heading_path의 마지막 제목이 존재하면 일치. **18건 이상** (라인 앵커 적용 시) / **15건 이상** (파일 단위 폴백 시). W1 결과에 따라 자동 결정 |
| 인용 규칙 | 본문 인용은 `[n]`(단일) / `[A1]`·`[B2]`(비교). 한 문장에 여러 인용 허용. 범위 밖 번호는 비활성 렌더(INV-08) |

---

## 8. 이용량·비용 정책

제한은 세 겹으로 건다: nginx(IP) → backend(사용자·세션) → ai-server(시스템 전체). Redis 없이 단일 인스턴스 메모리와 PostgreSQL로 구현하며, 재시작 시 분당 버킷이 초기화되는 것은 허용한다.

### 8.1 요청 제한

| 계층 | 대상 | 한도 | 초과 응답 | 저장소 |
| --- | --- | --- | --- | --- |
| nginx | `/api/v1/auth/**` IP당 | 10 req/분, burst 5 | 429 | nginx `limit_req` |
| nginx | `/api/v1/chat/**` IP당 | 30 req/분, burst 10 | 429 | nginx `limit_req` |
| nginx | 그 외 `/api/**` IP당 | 120 req/분, burst 30 | 429 | nginx `limit_req` |
| backend | 게스트 세션 | 5회/24시간 | `GUEST_QUOTA_EXCEEDED` | PostgreSQL |
| backend | 게스트 신규 세션 IP당 | 30개/시간 | `GUEST_SESSION_LIMIT` | PostgreSQL |
| backend | 로그인 사용자 분당 | 10 질문 | `RATE_LIMITED` + `Retry-After` | 메모리 토큰 버킷 |
| backend | 로그인 사용자 일일 | 100 질문(KST 00:00 초기화), 비교 모드는 2로 계산 | `DAILY_QUOTA_EXCEEDED` | 메시지 테이블 COUNT |
| backend | 동시 스트림 | 사용자당 2, 게스트 세션당 1 | `CONCURRENT_STREAM_LIMIT` | 메모리 카운터 |
| ai-server | 시스템 전체 동시 생성 | 20 (asyncio Semaphore). 대기열 없이 즉시 거절 | `AI_BUSY`(503) | 메모리 |
- 동시 생성 20은 초기값이며 E6 결과로 확정한다. 대기열을 두지 않는 이유는 2GiB 메모리에서 대기 연결이 쌓이면 OOM이 먼저 오기 때문이다.
- 관리자도 동일 한도를 적용한다. 평가 스크립트는 backend를 거치지 않고 ai-server 내부 API를 직접 호출하므로 사용자 한도의 영향을 받지 않는다.
- **11/18 전시회 당일 한정**: nginx `/api/v1/chat/**` 30 → 60 req/분(burst 20), 게스트 신규 세션 IP당 30 → 60개/시간. `scripts/exhibition-profile.sh apply`로 적용, 11/19 00:00 `reset`으로 원복. W6 리허설에서 수치 부족 시 `apply` 실행 전 파라미터 조정 가능

### 8.2 비용 상한

| 항목 | 정책 |
| --- | --- |
| OpenAI | 대시보드 월 사용 한도 20달러(하드), 이메일 알림 10달러. 실험 월(10월)만 30달러로 상향 가능 |
| AWS | Budgets 알림 50%·80%, 주 1회 잔여 크레딧 확인(기획서 9.5) |
| 평가 실행 | E3 응답은 `eval/cache/`에 (조건, 질문, 모델, prompt_version) 키로 캐시. 캐시 적중 시 API 호출 0 |
| 부하 테스트 | mock LLM만 사용. 실제 LLM은 S0 smoke 20회로 제한 |
| 사용량 기록 | 메시지별 prompt·completion 토큰을 저장하고 관리자 대시보드에 일별 합계 표시 |

---

## 9. 운영·프로필·오류 정책

### 9.1 프로필별 기능 매트릭스

| 기능 | local | staging | loadtest | prod |
| --- | --- | --- | --- | --- |
| 수집·임베딩 CLI | O | O | X | X (빈 미등록) |
| 관리자 재수집 트리거(P2) | O | O | X | X (`FORBIDDEN_IN_PROFILE`) |
| 인덱스 스냅샷 복원·활성화 | O | O | O | O |
| Mock LLM | O | X | O | X (감지 시 기동 실패) |
| Spring `/swagger-ui` | O | O | O | O (평가자 확인용, 인증 필요 API는 토큰 입력 필요) |
| FastAPI `/docs` | O | O | O | X (내부망에서도 비노출) |
| 관리자 시드 | O | O | O | O |

### 9.2 오류 응답 계약

- 스트림 시작 전 오류: HTTP 상태 + `{"code", "message", "request_id", "timestamp"}`.
- 스트림 시작 후 오류: `event: error` + `{"code", "message", "request_id", "partial": bool}` (INV-09).
- `message`는 사용자 표시용 한국어. 스택 트레이스·내부 호스트명은 노출하지 않는다.

| 코드 | HTTP | 발생 조건 | 클라이언트 처리 |
| --- | --- | --- | --- |
| `INVALID_REQUEST` | 400 | 입력 검증 실패 | 필드 오류 표시 |
| `AUTH_INVALID_CREDENTIALS` | 401 | 로그인 실패 | 동일 문구 표시 |
| `AUTH_TOKEN_EXPIRED` | 401 | Access 만료 | silent refresh 후 재시도 |
| `AUTH_REFRESH_REUSED` | 401 | Refresh 재사용 탐지 | 로그인 화면, "보안을 위해 로그아웃되었습니다" |
| `AUTH_REFRESH_CONFLICT` | 409 | 회전 경합 유예 내 재제출 | 1회 재시도 |
| `AUTH_LOCKED` | 429 | 로그인 5회 실패 | `Retry-After` 표시 |
| `FORBIDDEN` | 403 | 권한 없음(비관리자 → admin) | 접근 불가 화면 |
| `FORBIDDEN_IN_PROFILE` | 403 | 운영에서 수집 기능 호출 | 버튼 비활성 |
| `GUEST_MODE_NOT_ALLOWED` | 403 | 게스트 비교 모드 | 로그인 유도 |
| `CONVERSATION_NOT_FOUND` | 404 | 없음 또는 타인 대화 | 목록으로 이동 |
| `CONVERSATION_BUSY` | 409 | 대화 내 진행 중 메시지 존재 | 입력 비활성 유지 |
| `CONVERSATION_FULL` | 409 | 메시지 100개 도달 | 새 대화 버튼 |
| `SOURCE_UNAVAILABLE` | 409 | 비활성 버전으로 질문 | 읽기 전용 표시 |
| `GUEST_QUOTA_EXCEEDED` | 429 | 게스트 5회 소진 | 로그인 유도 모달 |
| `GUEST_SESSION_LIMIT` | 429 | IP당 게스트 세션 초과 | 로그인 유도 |
| `RATE_LIMITED` | 429 | 분당 한도 초과 | `Retry-After` 후 재시도 |
| `DAILY_QUOTA_EXCEEDED` | 429 | 일일 한도 초과 | 다음 날 안내 |
| `CONCURRENT_STREAM_LIMIT` | 429 | 동시 스트림 초과 | 진행 중 답변 완료 후 재시도 |
| `LLM_ERROR` | 502 | OpenAI 오류 | 재질문 버튼 |
| `COMPARE_PARSE_ERROR` | 502 | 비교 JSON 파싱 2회 실패 | 재질문 버튼 |
| `AI_UNAVAILABLE` | 503 | ai-server 연결 실패 | 잠시 후 재시도 |
| `AI_BUSY` | 503 | 시스템 동시 생성 20 초과 | 잠시 후 재시도 |
| `INDEX_NOT_ACTIVE` | 503 | ACTIVE run 없음(INV-01 위반, 장애) | 관리자 알림 |
| `UPSTREAM_TIMEOUT` | 504 | 첫 이벤트 15초·비교 30초 초과 | 재질문 버튼 |
| `EMBEDDING_MODEL_MISMATCH` | 500 | INV-03 위반 | 관리자 알림 |

### 9.3 SSE 이벤트 계약

| 이벤트 | 필드 |
| --- | --- |
| `meta` | request_id, conversation_id, message_id, source_key, ingest_run_id, commit_sha, ingested_at, rewritten_query, no_context, sources[{rank, heading_path, permalink, site_url, similarity}] |
| `token` | `t`(텍스트 조각) |
| `done` | status(COMPLETED/PARTIAL/NO_CONTEXT), status_reason, finish_reason, usage{prompt, completion}, latency{rewrite_ms, embed_ms, retrieve_ms, ttft_ms, total_ms}, invalid_citations[] |
| `error` | code, message, request_id, partial |
| 주석 `: ping` | 10초 하트비트, 클라이언트는 무시 |

계약은 `contracts/sse-events.schema.json`으로 두고 backend·ai-server 계약 테스트가 같은 파일을 읽는다.

### 9.4 관측·배포·백업

| 항목 | 정책 |
| --- | --- |
| 요청 추적 | nginx가 `X-Request-Id` 생성(없을 때) → backend → ai-server 전파. 모든 로그·메시지·오류 응답에 포함 |
| 로그 형식 | JSON 구조 로그. 질문 원문은 운영 로그에 남기지 않고 길이·해시만 기록(원문은 DB 이력에만). JWT·쿠키·API 키는 마스킹 |
| 헬스체크 | backend `/actuator/health`(DB 연결), ai-server `/internal/v1/health`(Chroma 로드·소스별 ACTIVE run 존재). Compose `healthcheck`로 의존 순서 제어 |
| 배포 | `deploy.sh <git-sha>`: 이미지 태그 = git SHA. 롤백 = 직전 SHA로 재실행. `latest` 태그 운영 사용 금지. 전시회 환경 전환·원복: `scripts/exhibition-profile.sh apply|reset` (11/18 적용, 11/19 00:00 원복) |
| DB 마이그레이션 | `app` 스키마는 Flyway(backend 소유), `ai` 스키마는 Alembic(ai-server 소유). 서로의 스키마에 쓰기 금지, 읽기는 backend가 `ai.sources`·`ai.index_pointers`만 조회 |
| 백업 | 일 1회 `pg_dump` → S3, 7일 보관. 인덱스는 스냅샷 자체가 백업. 복구 절차는 `docs/deployment.md`에 기록하고 W5에 1회 리허설 |
| 비밀 정보 | `.env`는 저장소 제외, `.env.example`만 커밋. CI에서 gitleaks 실패 시 병합 차단 |

---

## 10. 주요 상태 전이

상태는 DB 컬럼으로 저장하고, 전이는 표에 없는 경로를 코드에서 거부한다(전이 테이블 기반 `canTransition(from, to)` 단위 테스트 필수).

| 도메인 | 상태 |
| --- | --- |
| IngestRun (`ai.ingest_runs`) | `PENDING` → `COLLECTING` → `PROCESSING` → `EMBEDDING` → `VALIDATING` → `READY` → `ACTIVE` → `SUPERSEDED` → `PURGED` / 복원 경로 `RESTORING` → `VALIDATING` / 실패 `FAILED` → `PURGED` |
| Assistant 메시지 — 단일 (`app.messages`) | `PENDING` → `STREAMING` → `COMPLETED` · `PARTIAL` · `NO_CONTEXT` · `FAILED` |
| Assistant 메시지 — 비교 | `PENDING` → `PROCESSING` → `COMPLETED` · `NO_CONTEXT` · `FAILED` |
| Refresh 토큰 (`app.refresh_tokens`) | `ACTIVE` → `USED` · `REVOKED` (만료는 시각 비교로 판정, 상태로 저장하지 않음) |
| Refresh 패밀리 (`app.token_families`) | `ACTIVE` → `REVOKED` (만료는 시각 비교) |
| 게스트 세션 (`app.guest_sessions`) | `ACTIVE` → `EXHAUSTED` → 만료 / `ACTIVE` → 만료 (만료는 시각 비교) |
| 사용자 계정 (`app.users`) | `ACTIVE` ↔ `LOCKED`(시간 경과로 자동 해제) |
| 대화 (파생 상태, 저장하지 않음) | `OPEN` / `READ_ONLY`(메시지 100개 또는 소스 비활성) |

### 10.1 IngestRun

| From | To | 트리거 | 부수 효과 |
| --- | --- | --- | --- |
| — | PENDING | `make ingest SOURCE=…` (local·staging) | run id 발급, 파라미터 기록 |
| PENDING | COLLECTING | 수집 시작 | sparse checkout, `commit_sha` 기록 |
| COLLECTING | PROCESSING | 체크아웃 완료 | 전처리·섹션 분리·청킹, 누락 스니펫 기록 |
| PROCESSING | EMBEDDING | 청크 생성 완료 | 임베딩 API 호출, 토큰·비용 기록 |
| EMBEDDING | VALIDATING | 컬렉션 저장 완료 | 4.4 게이트 실행(10분 제한) |
| — | RESTORING | `make restore-index` (모든 프로필) | tar 해제, checksum 검증 |
| RESTORING | VALIDATING | checksum 일치 | 복원 검증 포함 게이트 실행 |
| VALIDATING | READY | 게이트 전 항목 통과 | 검증 리포트 저장 |
| READY | ACTIVE | `make activate-index RUN=…` | 포인터 UPDATE, 기존 ACTIVE → SUPERSEDED, reload 호출, 메타 캐시 무효화 |
| ACTIVE | SUPERSEDED | 다른 run 활성화 | 컬렉션 유지(롤백·in-flight 보호) |
| SUPERSEDED | ACTIVE | `make rollback-index` | 현재 ACTIVE → SUPERSEDED |
| SUPERSEDED | PURGED | 더 새로운 SUPERSEDED 발생 | 컬렉션 삭제, run 레코드는 보존 |
| PENDING~VALIDATING | FAILED | 단계 오류·게이트 실패·제한 시간 초과 | `failure_stage`, `failure_reason` 기록, 기존 ACTIVE 유지 |
| FAILED | PURGED | 24시간 경과 | 컬렉션 삭제 |

### 10.2 Assistant 메시지

| From | To | 조건 | status_reason |
| --- | --- | --- | --- |
| — | PENDING | 요청 검증·한도 통과 | — |
| PENDING | STREAMING | `meta` 수신(단일) | — |
| PENDING | PROCESSING | ai-server 호출 시작(비교) | — |
| PENDING | NO_CONTEXT | top-1 < τ | `LOW_SIMILARITY` |
| PENDING | FAILED | 연결 실패·첫 이벤트 타임아웃·5xx·클라이언트 취소 | `AI_UNAVAILABLE` · `UPSTREAM_TIMEOUT` · `LLM_ERROR` · `CLIENT_ABORTED` |
| STREAMING | COMPLETED | `done`, finish_reason=stop | — |
| STREAMING | NO_CONTEXT | sentinel 감지 | `LLM_ABSTAIN` |
| STREAMING | PARTIAL | 토큰 ≥ 1 상태에서 중단 | `CLIENT_ABORTED` · `UPSTREAM_IDLE_TIMEOUT` · `LLM_ERROR` · `LENGTH` · `MAX_DURATION` |
| STREAMING | FAILED | 토큰 0 상태에서 중단, 또는 150초 고착 | 위와 동일 · `STALE` · `PERSIST_ERROR` |
| PROCESSING | COMPLETED | 검증된 JSON 저장 | — |
| PROCESSING | NO_CONTEXT | 양쪽 top-1 < τ | `LOW_SIMILARITY` |
| PROCESSING | FAILED | 30초 초과·파싱 2회 실패·ai-server 오류 | `UPSTREAM_TIMEOUT` · `COMPARE_PARSE_ERROR` · `AI_UNAVAILABLE` |

종결 상태 4개에서 나가는 전이는 없다(INV-12). 게스트 요청은 DB에 저장하지 않지만 동일 상태 모델을 `guest_usage_log.status`에 사용한다.

### 10.3 인증 관련

| 도메인 | From | To | 트리거 |
| --- | --- | --- | --- |
| Refresh 토큰 | — | ACTIVE | 로그인·회전 |
| Refresh 토큰 | ACTIVE | USED | 회전 성공 |
| Refresh 토큰 | ACTIVE·USED | REVOKED | 로그아웃, 재사용 탐지(패밀리 전체), 패밀리 10개 초과 |
| 패밀리 | ACTIVE | REVOKED | 로그아웃, 재사용 탐지, 초과 정리 |
| 게스트 세션 | — | ACTIVE | 최초 질문 |
| 게스트 세션 | ACTIVE | EXHAUSTED | used_count = 5 |
| 게스트 세션 | EXHAUSTED | ACTIVE | 환불로 used_count < 5 (meta 이전 서버 오류) |
| 사용자 | ACTIVE | LOCKED | 15분 내 5회 실패 |
| 사용자 | LOCKED | ACTIVE | 잠금 15분 경과(조회 시 판정) |

---

## 11. 비기능 요구사항

| 구분 | 요구사항 | 목표 (확정 필요) |
| --- | --- | --- |
| 성능 | TTFT(단일, 배포 환경 20회) | p50 ≤ 3초, p95 ≤ 5초 — 확정 |
| 성능 | `meta` 도착 시간(단일) | p95 ≤ 1.5초 — 측정 후 확정 |
| 성능 | 검색(retrieve) 지연 | p95 ≤ 500ms — 확정 |
| 성능 | 질의 재작성 지연 | p95 ≤ 1.5초, 폴백률 ≤ 5% — 측정 후 확정 |
| 성능 | 비교 모드 전체 응답 | p50 ≤ 12초 — 확정, 타임아웃 30초 |
| 성능 | 로그인 응답(BCrypt 포함) | p95 ≤ 300ms — 측정 후 확정 |
| 용량 | 동시 스트림(mock LLM, t3.small) | 10 VU 오류율 < 1%, `meta` p95 < 1초 — 확정 |
| 용량 | 시스템 동시 생성 상한 | 20 — E6 후 확정 |
| 안정성 | 30분 soak | 메모리 증가 < 10%, 연결 누수 0 — 확정 |
| 안정성 | 인덱스 교체 중 질의 | 교체 전후 60초 구간 요청 실패 0건 — 확정 |
| 안정성 | STREAMING 고착 메시지 | 스위퍼 실행 후 150초 초과 STREAMING 0건 |
| 정확성 | 버전 혼입(격리 조건) | E1 혼입 0건, INV-02 2차 검증 폐기 로그 0건 — 확정 |
| 정확성 | permalink 유효율 | 100% (VALIDATING 전수) — 확정 |
| 정확성 | 비교 모드 인용 | 존재하지 않는 인용 0건(후처리 후), 10건 수동 평가 — 확정 |
| 보안 | 전송 | HTTPS 전용, HTTP → HTTPS 301, HSTS max-age 1년 |
| 보안 | 토큰 저장 | Access는 메모리, Refresh·게스트 쿠키 HttpOnly·Secure·SameSite=Strict — 확정 |
| 보안 | 인증 경로 | 재사용 탐지·잠금·동일 실패 메시지 단위 테스트 100% 통과 |
| 보안 | 비밀 정보 | gitleaks CI 통과, 저장소 내 키 0건 |
| 보안 | 헤더 | CSP `default-src 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`. CORS 미허용(동일 출처) |
| 자원 | 메모리 합계 | 상주 ≤ 1.75GB, 스왑 사용 ≤ 256MB(평시) — W5 실측 후 확정 |
| 자원 | 디스크 | EBS 20GiB 중 사용률 ≤ 70% |
| 운영 | 환경 재현 | README 절차로 30분 이내 기동 — 확정 |
| 운영 | 실험 재현 | `make eval` 한 줄로 E1·E2 CSV 생성 — 확정 |
| 운영 | 복구 | RPO 24시간, RTO 1시간(백업 복원 리허설 W5 1회) |
| 관측 | 요청 추적 | 모든 로그·오류·메시지에 request_id 100% 포함 |
| 관측 | 단계별 지연 | 모든 assistant 메시지에 5종 지연 필드 기록 |
| 비용 | OpenAI | 월 20달러 이하(10월 30달러) |
| 비용 | AWS | 가입 크레딧 100달러 이내 |

---

## 미결정 사항

모든 항목은 현재 가정값으로 개발을 진행하고, 결정 시 본 문서와 관련 ADR을 함께 갱신한다.

| 항목 | 현재 가정값 | 결정 시점 | 결정 방법 |
| --- | --- | --- | --- |
| NO_CONTEXT 임계값 τ | 0.30 (개발용) | **W2 (10/14)** | E1 부속: Q-oos·Q-ret similarity 분포에서 오탐(범위 내 질문이 NO_CONTEXT)·미탐(범위 외가 통과) 균형점. 결정 후 4.4 스모크 기준도 동일 τ로 재실행 |
| 청킹 전략 | 전략 B (초기 개발용) | **W3 (10/21)** | E2 사전 결정 규칙(`eval/decision_rules.md`, eval-v1 태그 이전 커밋으로 확정): Hit@5 최고 전략. 1·2위 차이 < 3%p이면 평균 토큰 수 적은 전략 |
| Top-K | 5 (초기 개발용) | **W3 (10/21)** | E2 결정 규칙: Hit@K 증가폭 < 2%p인 최소 K |
| 컨텍스트 토큰 예산 | 3,000 (최대 상한) | **W3 (10/21)** | E2 확정 후 공식 적용: `min(3000, K_final × avg_chunk_tokens × 1.15)`. 상한 3,000은 고정, 실제 예산은 하향 가능 |
| 시스템 동시 생성 상한 | 20 | **W6 (11/11)** | E6 S2(ramp-up)·S3(sustained) 결과. 오류율 < 1% + `meta` p95 < 1초를 만족하는 최대 VU를 상한으로 설정 |
| 1.x 스니펫 누락 허용 기준 | 누락 파일 비율 ≤ 5% | **W1 (10/7)** | 스파이크 측정으로 실제 누락 비율 확인. 5% 초과 시 허용 기준 상향하거나 해당 파일 제외 목록 작성. 제외된 파일은 VALIDATING 청크 수 기준 ±30% 판정에서 제외 |

---

end.
