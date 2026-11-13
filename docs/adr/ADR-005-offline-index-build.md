# ADR-005: 인덱스 빌드 오프라인 분리

## Status
Draft

## Date
2026-11-14

## Context

LangChain 공식 문서를 수집·임베딩하여 Chroma에 적재하는 "인덱스 빌드" 작업은 다음 특성을 가진다:

- **소요 시간**: 문서 크롤링 + 청킹 + OpenAI 임베딩 API 호출 → 수십 분
- **비용**: 임베딩 API 호출 비용 발생 (최초 1회 + 재인덱싱 시)
- **빈도**: LangChain 문서 갱신 시 또는 수동 트리거 (월 1회 미만 예상)
- **충돌**: ADR-002(임베디드 Chroma)로 인해 빌드 중 서비스 동시 운영 불가

온라인 빌드(서비스 기동 시 자동 빌드) 옵션도 고려했으나:
- 콜드 스타트 수십 분 → 서비스 불가 시간 발생
- 비용 통제 불가 (버그 시 반복 호출)

## Decision

**인덱스 빌드를 서비스 프로세스와 완전히 분리**한다.

```
[빌드 파이프라인]
make build-index VERSION=v03
  → scripts/ingest/crawl.py      # GitHub에서 문서 크롤링
  → scripts/ingest/chunk.py      # 청킹 + 메타데이터 부착
  → scripts/ingest/embed.py      # OpenAI 임베딩 호출
  → scripts/ingest/load.py       # Chroma 적재
  → scripts/ingest/validate.py   # permalink HTTP 200 검증
  → chroma_data/ 스냅샷 생성 (.tar.gz)

[서비스 기동]
make restore-index               # 스냅샷 압축 해제
docker compose up ai-server      # Chroma 임베디드 모드로 기동
```

스냅샷은 CI/CD 아티팩트 또는 S3에 저장. 서비스는 스냅샷 복원 후 기동.

## Consequences

**장점**
- 서비스 콜드 스타트 없음
- 빌드 비용 1회만 지불 → 이후 스냅샷 재사용
- CI/CD에서 `make build-index` 트리거 가능 (GitHub Actions `workflow_dispatch`)
- 빌드 실패 시 이전 스냅샷으로 롤백 가능

**단점 / 트레이드오프**
- 빌드 환경과 서비스 환경의 Chroma 버전 일치 필요 (uv.lock으로 고정)
- 재인덱싱 시 서비스 일시 중단 필요 (임베디드 쓰기 잠금) → 블루그린 배포 고려 필요(R-2+)

**관련 ADR**
- ADR-002: Chroma 임베디드 모드 (쓰기 잠금 근거)
- ADR-006: 소스 어댑터 (크롤러 구조)
- ADR-007: SHA 고정 (스냅샷 추적성)
