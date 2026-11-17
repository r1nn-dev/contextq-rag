"""Source Adapter 출력 모델 — interfaces.md §2.1 `Section`·`NormalizedDocument`."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    heading_path: str  # "Agents > Tools > Defining tools"
    text: str  # 전처리 완료 본문 (섹션 헤더 줄 포함)
    line_numbers: tuple[int, ...]  # text 각 줄의 원문 라인 번호 (1부터)

    def __post_init__(self) -> None:
        if len(self.line_numbers) != len(self.text.split("\n")):
            raise ValueError("line_numbers 길이가 text 줄 수와 다릅니다")

    @property
    def line_start(self) -> int:
        return self.line_numbers[0]

    @property
    def line_end(self) -> int:
        return self.line_numbers[-1]


@dataclass(frozen=True)
class NormalizedDocument:
    file_path: str  # 저장소 루트 기준 경로
    title: str
    doc_type: str  # "md" | "mdx" | "ipynb"
    site_url: str  # 보조 링크 (불변 보장 없음)
    sections: tuple[Section, ...]
