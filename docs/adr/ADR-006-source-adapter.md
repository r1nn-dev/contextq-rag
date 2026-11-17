# ADR-006: 소스 수집 어댑터 인터페이스 설계

## Status
Accepted

## Date
2026-11-14 (2026-11-17 개정: 수집 방식을 sparse checkout으로 변경, Accepted)

## Context

LangChain 공식 문서는 버전마다 저장소·포맷·URL 체계가 다르다(`docs/planning/policy.md` > §3.1).

| 버전 | 저장소 · ref · 경로 | 포맷 |
| --- | --- | --- |
| v0.3 | `langchain-ai/langchain` · `v0.3` · `docs/docs/` | Docusaurus (`.md`, `.mdx`, `.ipynb`) |
| v1.x | `langchain-ai/docs` · `main` · `src/oss/` | Mintlify (`.mdx` + 스니펫) |

수집 방법 후보:

- **옵션 A**: 문서 사이트 웹 크롤링 → robots.txt, 렌더링된 HTML 파싱 복잡도
- **옵션 B**: GitHub REST API로 raw 파일 수집 → 파일 수(수천 개)만큼 API 호출, rate limit 관리 필요
- **옵션 C**: `git sparse-checkout`으로 문서 디렉터리만 받아 로컬 파싱 → 호출 1회, 커밋 SHA를 그대로 얻음

## Decision

**git sparse checkout으로 문서 디렉터리만 수집**하고, 포맷 차이는 **버전별 Source Adapter**가 흡수한다.

- 수집 대상(저장소·ref·문서 경로)은 코드가 아니라 `ai.sources` 카탈로그에서 읽는다.
- 수집 단계는 체크아웃한 커밋의 40자 SHA를 run에 기록한다(ADR-007).
- Adapter는 포맷별로 하나씩 둔다: `DocusaurusAdapter`(v0.3), `MintlifyAdapter`(v1.x). 카탈로그의 `adapter_class`로 선택한다.
- Adapter는 전처리 규칙(`policy.md` > §4.3)을 적용한 정규화 문서(`NormalizedDocument`: 파일 경로, 제목, 섹션 목록[heading_path, 본문, 원문 라인 범위], 문서 유형, 사이트 URL)를 돌려준다. 청킹·임베딩 계층은 포맷을 모른다.

```python
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

class SourceAdapter(Protocol):
    def iter_documents(self, root: Path) -> Iterator[NormalizedDocument]:
        """체크아웃 루트 아래 문서를 전처리해 정규화 문서로 순회한다."""
        ...
```

## Consequences

**장점**
- `SourceAdapter` 인터페이스 뒤로 포맷별 구현을 분리 — 신규 프레임워크는 Adapter 구현 + 카탈로그 행 추가로 확장(`policy.md` > §3.2)
- 체크아웃 1회로 수집이 끝나 API rate limit 영향이 없다
- 체크아웃 결과가 곧 커밋 SHA 고정 원본이라 재현성이 보장된다

**단점 / 트레이드오프**
- 수집 환경에 `git`과 네트워크가 필요하다 (오프라인 빌드 환경에서 미리 수집)
- 체크아웃 디렉터리(`data/raw/`)는 커밋하지 않으므로 재현하려면 같은 SHA로 다시 받아야 한다

**관련 ADR**
- ADR-007: SHA 고정 (수집 시점 SHA 기록)
- ADR-005: 오프라인 인덱스 빌드 (어댑터 사용 시점)
