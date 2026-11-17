# ADR-007: GitHub 커밋 SHA 고정 출처 추적

## Status
Accepted

## Date
2026-11-14 (2026-11-17 개정: 메타데이터 필드·라인 앵커·전수 검증을 정책서 기준으로 정리, Accepted)

## Context

RAG 시스템에서 출처 추적(provenance) 신뢰성 요건:

1. **재현성**: "이 답변이 어느 버전 문서 기준인가?"를 명확히 보장해야 함
2. **링크 유효성**: 사용자에게 제공하는 permalink가 클릭 시 실제로 열려야 함
3. **드리프트 방지**: 인덱스 빌드 후 원본 문서가 수정되어도 출처 URL이 불변이어야 함

단순 `main` 브랜치 URL(`github.com/.../blob/main/...`) 사용 시:
- 문서 수정·이동 시 링크 404
- 답변 근거가 된 버전을 특정 불가

## Decision

**모든 청크 메타데이터에 수집 시점 커밋 SHA를 고정**하여 permalink를 생성한다. 필드 이름과 필수 여부는 `docs/planning/policy.md` > §4.2를 따른다.

```python
def make_permalink(repo: str, commit_sha: str, file_path: str,
                   line_start: int | None, line_end: int | None) -> str:
    base = f"https://github.com/{repo}/blob/{commit_sha}/{file_path}"
    if line_start is None or line_end is None:   # .ipynb는 파일 단위
        return base
    return f"{base}?plain=1#L{line_start}-L{line_end}"
```

- `commit_sha`는 40자 전체 SHA다. 브랜치명(`main`, `v0.3`)이 들어간 URL은 저장 단계에서 거부한다(INV-05).
- `file_path`는 저장소 루트 기준 경로다(예: `src/oss/langchain/agents.mdx`).
- `.md`·`.mdx`는 원문 라인 범위 앵커(`?plain=1#L{start}-L{end}`)를 붙이고, `.ipynb`는 파일 단위 permalink만 만든다.

**빌드 시 permalink 검증 — 전수** (`policy.md` > §4.4):

- 파일 단위로 중복을 제거한 permalink 전부에 HTTP 요청을 보내 200을 확인한다.
- GitHub 토큰을 사용하고 초당 5건으로 제한한다.
- 1건이라도 실패하면 VALIDATING 게이트 실패(FAILED)이며 기존 ACTIVE는 유지된다.

## Consequences

**장점**
- permalink 영구 불변 — 인덱스 스냅샷과 1:1 대응
- 사용자가 클릭하면 답변 근거가 된 정확한 버전·라인의 문서 확인 가능
- 전수 검증이라 "샘플 밖 깨진 링크"가 남지 않는다
- 보고서/발표에서 "출처의 신뢰성" 항목 근거로 활용 가능

**단점 / 트레이드오프**
- Full SHA 40자 → Chroma 메타데이터 용량 증가 (무시 가능 수준)
- 전수 검증은 파일 수(수백 개) ÷ 초당 5건만큼 시간이 걸린다 → 파일 단위 중복 제거로 줄이고 게이트 제한 시간(10분) 안에서 실행
- 인덱스 재빌드 없이 최신 문서 반영 불가 (설계상 의도된 제약)

**관련 ADR**
- ADR-006: 소스 어댑터 (SHA 수집 주체)
- ADR-005: 오프라인 인덱스 빌드 (validate 단계에 포함)
