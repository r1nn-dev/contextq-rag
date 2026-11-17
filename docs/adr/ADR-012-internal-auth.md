# ADR-012: 서비스 간 내부 인증 — Shared Token

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 관련 이슈 | #{이슈 번호} |

---

## 컨텍스트

ADR-001에서 채택한 이중 서버 구조(Spring Boot 8080 ↔ FastAPI 8000)에서
서버 간 내부 HTTP 호출 시 별도 인증이 없으면 FastAPI 엔드포인트가 외부에서
직접 호출 가능해진다. 외부 클라이언트용 JWT를 그대로 사용하면 토큰 탈취 시
RAG 파이프라인 직접 접근이 가능하므로 신뢰 경계를 분리할 메커니즘이 필요하다.

단일 개발자 운영 환경으로 로컬·운영 모두 추가 설정을 최소화해야 한다.

---

## 결정 근거

- 구현 단순성 — 단일 개발자가 유지·운영 가능한가
- 로컬 개발 오버헤드 최소화
- 환경 변수 로테이션 가능성 (재빌드 없이 토큰 교체)
- 보안 강도 — MVP 범위 내 허용 가능 수준

---

## 고려한 옵션들

- **옵션 A**: JWT 그대로 사용 (서비스 계정 JWT 발급)
- **옵션 B**: Shared Token (`X-Internal-Token` 헤더)
- **옵션 C**: mTLS (상호 TLS 인증)

---

## 결정

**옵션 B — `X-Internal-Token` Shared Token** 을 선택한다.

구현이 단순하고 환경 변수 로테이션이 가능하며, 단일 개발자 운영 환경에서
mTLS의 추가 설정 복잡도를 감수할 필요가 없다.

---

## 결과

### 긍정적 영향

- FastAPI `Depends()` 미들웨어 10줄 이내로 구현 완료 가능
- `INTERNAL_TOKEN` 환경 변수 교체만으로 로테이션 — 재빌드·재배포 불필요
- 로컬 개발 환경 추가 인프라 설정 없음

### 부정적 영향 / 트레이드오프

- Shared Token 탈취 시 모든 내부 엔드포인트 접근 가능
  → 운영 환경에서는 네트워크 레벨 격리(VPC, 보안 그룹) 필수
- mTLS 대비 보안 강도 낮음 (MVP 단계 수용 가능 범위)

### 후속 작업

- [ ] FastAPI `verify_internal_token` Depends 구현 (ai-server 작업 시)
- [ ] Spring Boot `InternalTokenInterceptor` 구현 (backend 작업 시)
- [ ] 운영 환경 VPC·보안 그룹으로 FastAPI 포트 외부 차단 (배포 작업 시)

---

## 옵션별 장단점

### 옵션 A: JWT 그대로 사용

| | 내용 |
| --- | --- |
| 장점 | 추가 토큰 관리 불필요 |
| 단점 | 외부용 토큰과 신뢰 경계 미분리 — 탈취 시 전체 API 접근 가능 |

### 옵션 B: Shared Token

| | 내용 |
| --- | --- |
| 장점 | 구현 단순, 환경 변수 로테이션, 로컬 오버헤드 없음 |
| 단점 | 토큰 탈취 시 내부 엔드포인트 전체 노출 → 네트워크 격리 필수 |

### 옵션 C: mTLS

| | 내용 |
| --- | --- |
| 장점 | 보안 강도 높음, 토큰 탈취 위협 없음 |
| 단점 | 로컬 인증서 발급·관리 필요, 단일 개발자 운영 복잡도 과도 |

---

## 연관 ADR

- [ADR-001: 이중 서버 구조 — FastAPI + Spring Boot](../adr/ADR-001-dual-server.md)
- [ADR-003: SSE 스트리밍 방식](../adr/ADR-003-sse-fetch-stream.md)

---

## 참조

- `docs/ops/env-reference.md §1.5` — INTERNAL_TOKEN 상세 설명
- `ai-server/src/config/settings.py` — `internal_token` 필드 (구현 확인됨)

---

## 미결 사항

- [ ] 운영 환경 네트워크 격리 방식 확정 (배포 설계 시)