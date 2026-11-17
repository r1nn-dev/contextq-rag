"""Source Adapter 인터페이스와 레지스트리 (ADR-006, doc-source.md §3).

파이프라인은 카탈로그 `ai.sources.adapter_class` 이름으로 Adapter를 고른다.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.domain.documents import NormalizedDocument


@dataclass(frozen=True)
class MissingSnippet:
    file_path: str  # 스니펫을 참조한 문서
    component: str  # 태그 이름. 예: AgentsIntroPy
    import_path: str  # import 경로. 예: /snippets/code-samples/agents-intro-py.mdx


@dataclass
class AdapterReport:
    """전처리 부산물 — 파이프라인이 run 리포트와 ingest_runs 컬럼에 남긴다."""

    files_read: int = 0
    files_by_type: dict[str, int] = field(default_factory=dict)
    snippet_references: int = 0
    missing_snippets: list[MissingSnippet] = field(default_factory=list)

    def count_file(self, doc_type: str) -> None:
        self.files_read += 1
        self.files_by_type[doc_type] = self.files_by_type.get(doc_type, 0) + 1

    @property
    def files_with_missing_snippets(self) -> int:
        return len({m.file_path for m in self.missing_snippets})


class SourceAdapter(Protocol):
    report: AdapterReport

    def iter_documents(self, root: Path) -> Iterator[NormalizedDocument]:
        """체크아웃 루트(저장소 루트) 아래 포함 경로의 문서를 전처리해 순회한다."""
        ...


@dataclass(frozen=True)
class AdapterContext:
    """Adapter 생성 인자 — 카탈로그 행에서 만든다."""

    doc_path: str  # 저장소 루트 기준 문서 루트. 예: "src/oss/"


class AdapterNotRegisteredError(LookupError):
    """카탈로그의 adapter_class가 레지스트리에 없다 — PROCESSING 실패."""


AdapterFactory = Callable[[AdapterContext], SourceAdapter]
_REGISTRY: dict[str, AdapterFactory] = {}


def register_adapter(name: str) -> Callable[[AdapterFactory], AdapterFactory]:
    def decorator(factory: AdapterFactory) -> AdapterFactory:
        _REGISTRY[name] = factory
        return factory

    return decorator


def create_adapter(adapter_class: str, context: AdapterContext) -> SourceAdapter:
    # 레지스트리는 각 Adapter 모듈 import 시 채워진다
    import src.adapters.registry  # noqa: F401

    try:
        factory = _REGISTRY[adapter_class]
    except KeyError as exc:
        raise AdapterNotRegisteredError(f"등록되지 않은 Adapter입니다: {adapter_class}") from exc
    return factory(context)
