# ADR-006: 소스 수집 어댑터 인터페이스 설계

## Status
Draft

## Date
2026-11-14

## Context

LangChain 공식 문서는 GitHub 리포지토리에서 Markdown 파일로 관리된다. 수집 방법:

- **옵션 A**: `langchain.readthedocs.io` 웹 크롤링 → robots.txt, 렌더링된 HTML 파싱 복잡도
- **옵션 B**: GitHub API로 raw Markdown 직접 수집 → 구조적, SHA 고정 가능
- **옵션 C**: `langchain-ai/langchain` 리포 클론 후 로컬 파싱 → 용량 큼

## Decision

**GitHub API 기반 소스 어댑터**를 채택한다. 어댑터 인터페이스를 정의하여 소스 교체 가능하게 한다.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class RawDocument:
    content: str          # Markdown 원문
    source_path: str      # 리포 내 상대 경로 (e.g. "docs/concepts/agents.md")
    commit_sha: str       # 수집 시점 커밋 SHA
    repo: str             # "langchain-ai/langchain"
    version_tag: str      # "v0.3" | "v1.x"

class SourceAdapter(ABC):
    @abstractmethod
    def fetch_documents(self, version: str) -> list[RawDocument]:
        ...

class GitHubSourceAdapter(SourceAdapter):
    """GitHub REST API를 통해 특정 커밋 SHA의 Markdown 문서를 수집"""
    def fetch_documents(self, version: str) -> list[RawDocument]:
        ...
```

수집 대상:
- v0.3: `langchain-ai/langchain` 리포의 `docs/` 디렉토리 (고정 SHA)
- v1.x: `langchain-ai/langchain-docs` 리포의 최신 `docs/` 디렉토리 (고정 SHA)

## Consequences

**장점**
- `SourceAdapter` 인터페이스 뒤로 구현 교체 가능 (GitHub → 로컬 → 다른 소스)
- GitHub API rate limit 대응: `GITHUB_TOKEN` 환경 변수 사용 시 5000 req/hr
- raw Markdown 수집 → 불필요한 HTML 파싱 없음

**단점 / 트레이드오프**
- GitHub API 의존 → 네트워크 없는 환경에서 빌드 불가 (오프라인 빌드 환경에서 미리 수집 필요)
- 대용량 리포의 경우 API 호출 수 증가 → rate limit 주의

**관련 ADR**
- ADR-007: SHA 고정 (수집 시점 SHA 기록)
- ADR-005: 오프라인 인덱스 빌드 (어댑터 사용 시점)
