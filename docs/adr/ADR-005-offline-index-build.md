# ADR-005: 인덱스 빌드 오프라인 분리

## Status
Accepted

## Date
2026-11-14 (2026-11-17 개정: 명령·코드 위치를 정책서 기준으로 정리, Accepted)

## Context

LangChain 공식 문서를 수집·임베딩하여 Chroma에 적재하는 "인덱스 빌드" 작업은 다음 특성을 가진다:

- **소요 시간**: 문서 수집 + 청킹 + OpenAI 임베딩 API 호출 → 수십 분
- **비용**: 임베딩 API 호출 비용 발생 (최초 1회 + 재인덱싱 시)
- **빈도**: LangChain 문서 갱신 시 또는 수동 트리거 (월 1회 미만 예상)
- **충돌**: ADR-002(임베디드 Chroma)로 인해 빌드 중 서비스 동시 운영 불가

온라인 빌드(서비스 기동 시 자동 빌드) 옵션도 고려했으나:
- 콜드 스타트 수십 분 → 서비스 불가 시간 발생
- 비용 통제 불가 (버그 시 반복 호출)

## Decision

**인덱스 빌드를 서비스 프로세스와 완전히 분리**한다. 빌드는 local·staging에서만 실행하고, 운영(prod)은 검증된 스냅샷의 복원·활성화만 한다(`docs/planning/policy.md` > §4.5, INV-17).

```
[빌드 — local·staging 전용]
make ingest SOURCE=langchain_v03
  → PENDING     run 발급, 파라미터 기록
  → COLLECTING  git sparse checkout, commit_sha 기록 (ADR-006, ADR-007)
  → PROCESSING  Source Adapter 전처리 → 청킹
  → EMBEDDING   OpenAI 임베딩 → run 전용 컬렉션 저장 (ADR-004)
  → VALIDATING  검증 게이트 (policy.md §4.4)
  → READY

make activate-index RUN=<id>      # READY → ACTIVE, 포인터 교체
make rollback-index SOURCE=<key>  # 직전 SUPERSEDED → ACTIVE (1세대)

[운영 — 모든 프로필]
make restore-index                # 스냅샷 복원 → VALIDATING → READY → 활성화
```

- 코드 위치: `ai-server/src/ingest/` (CLI 엔트리포인트 포함). Makefile 타깃은 이 CLI를 호출한다.
- 상태 전이는 `docs/planning/policy.md` > §10.1 표를 따르며, 표에 없는 전이는 코드에서 거부한다.
- prod 프로필에서는 수집·임베딩 명령을 등록하지 않는다. 활성화·롤백·복원만 사용할 수 있다.
- 스냅샷은 `snapshot-{source_key}-run{id}.tar.gz`(Chroma 컬렉션 디렉터리 + `manifest.json`)이며 S3에 run별로 보관한다(`policy.md` > §4.5).

## Consequences

**장점**
- 서비스 콜드 스타트 없음
- 빌드 비용 1회만 지불 → 이후 스냅샷 재사용
- 빌드 실패 시 기존 ACTIVE를 건드리지 않으므로 서비스가 그대로 유지된다(RAG-10)
- 활성화·롤백이 포인터 교체라 재빌드 없이 즉시 되돌릴 수 있다

**단점 / 트레이드오프**
- 빌드 환경과 서비스 환경의 Chroma 버전 일치 필요 (`uv.lock`으로 고정)
- 재인덱싱 결과를 운영에 반영하려면 스냅샷 업로드·복원 절차가 필요하다

**관련 ADR**
- ADR-002: Chroma 임베디드 모드 (쓰기 잠금 근거)
- ADR-004: run 단위 컬렉션과 활성 포인터
- ADR-006: 소스 어댑터 (수집·전처리 구조)
- ADR-007: SHA 고정 (스냅샷 추적성)
