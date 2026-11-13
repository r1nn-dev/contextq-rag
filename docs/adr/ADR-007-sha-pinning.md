# ADR-007: GitHub 커밋 SHA 고정 출처 추적

## Status
Draft

## Date
2026-11-14

## Context

RAG 시스템에서 출처 추적(provenance) 신뢰성 요건:

1. **재현성**: "이 답변이 어느 버전 문서 기준인가?"를 명확히 보장해야 함
2. **링크 유효성**: 사용자에게 제공하는 `source_url`이 클릭 시 실제로 열려야 함
3. **드리프트 방지**: 인덱스 빌드 후 원본 문서가 수정되어도 출처 URL이 불변이어야 함

단순 `main` 브랜치 URL(`github.com/.../blob/main/...`) 사용 시:
- 문서 수정·이동 시 링크 404
- 답변 근거가 된 버전을 특정 불가

## Decision

**모든 청크 메타데이터에 인덱스 빌드 시점 커밋 SHA를 고정**하여 permalink를 생성한다.

```python
@dataclass
class ChunkMetadata:
    source_path: str    # "docs/concepts/agents.md"
    repo: str           # "langchain-ai/langchain"
    commit_sha: str     # "a3f9c12b..."  (40자 full SHA)
    version_tag: str    # "v0.3" | "v1.x"
    chunk_index: int    # 동일 파일 내 청크 순서
    heading: str        # 가장 가까운 ## 제목 (검색 결과 표시용)

def make_permalink(meta: ChunkMetadata) -> str:
    return (
        f"https://github.com/{meta.repo}/blob/"
        f"{meta.commit_sha}/{meta.source_path}"
    )
```

**빌드 시 permalink HTTP 200 검증** (샘플링):

```python
import httpx

async def validate_permalink(url: str) -> bool:
    async with httpx.AsyncClient() as client:
        resp = await client.head(url, follow_redirects=True)
        return resp.status_code == 200
```

빌드 파이프라인 `validate` 단계에서 청크 중 10% 무작위 샘플링하여 검증.
실패 비율 > 1% 시 빌드 중단.

## Consequences

**장점**
- `source_url` 영구 불변 — 인덱스 스냅샷과 1:1 대응
- 사용자가 클릭하면 답변 근거가 된 정확한 버전의 문서 확인 가능
- 보고서/발표에서 "출처의 신뢰성" 항목 근거로 활용 가능

**단점 / 트레이드오프**
- Full SHA 40자 → Chroma 메타데이터 용량 증가 (무시 가능 수준)
- GitHub API rate limit 내에서 샘플 검증 추가 소요
- 인덱스 재빌드 없이 최신 문서 반영 불가 (설계상 의도된 제약)

**관련 ADR**
- ADR-006: 소스 어댑터 (SHA 수집 주체)
- ADR-005: 오프라인 인덱스 빌드 (validate 단계에 포함)
