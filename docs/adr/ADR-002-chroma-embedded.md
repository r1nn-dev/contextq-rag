# ADR-002: Chroma 임베디드 모드 채택

## Status
Draft

## Date
2026-11-14

## Context

벡터 스토어 선택지를 검토했다:

| 옵션 | 특징 | 단점 |
|---|---|---|
| Chroma (임베디드) | ai-server 프로세스 내 인스턴스, 별도 컨테이너 불필요 | 멀티 프로세스 동시 접근 불가 |
| Chroma (클라이언트-서버 모드) | HTTP로 별도 Chroma 서버와 통신 | 컨테이너 추가, 네트워크 오버헤드 |
| Pinecone / Weaviate | 완전 관리형 클라우드 서비스 | 비용, 외부 의존성, 오프라인 불가 |
| pgvector (PostgreSQL 확장) | 기존 PostgreSQL에 벡터 기능 추가 | 임베딩 검색 성능이 Chroma 대비 낮음 |

이 프로젝트는 단일 ai-server 프로세스에서만 Chroma에 접근하며, 인덱스는 오프라인 빌드 후 스냅샷으로 복원된다(ADR-005 참조).

## Decision

**Chroma 임베디드 모드**를 사용한다.

```python
import chromadb

client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
```

- `CHROMA_PERSIST_DIR`: 환경 변수로 주입 (`./chroma_data` 기본값)
- 프로덕션: EBS 볼륨에 마운트
- 로컬: `.gitignore` 등록된 `chroma_data/` 디렉토리

## Consequences

**장점**
- 별도 Chroma 서버 컨테이너 불필요 — `docker-compose.yml` 단순화
- 네트워크 직렬화 오버헤드 없음 → 검색 레이턴시 최소화
- `uv sync` 한 번으로 모든 의존성 설치 완료

**단점 / 트레이드오프**
- ai-server 인스턴스를 수평 확장(여러 프로세스)하면 Chroma 데이터 불일치 발생 → 수평 확장 시 클라이언트-서버 모드 전환 필요
- 인덱스 빌드와 서비스 프로세스를 동일 머신에서 동시에 실행 불가 (쓰기 잠금)

**관련 ADR**
- ADR-004: 버전별 컬렉션 분리
- ADR-005: 오프라인 인덱스 빌드 (빌드 중 서버 중단 이슈 처리)
