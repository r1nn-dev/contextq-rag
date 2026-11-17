"""평가 질문셋 로더와 스키마 검증 — eval-scenarios.md §2·§3.

- 질문 1개 = YAML 파일 1개: `eval/questions/{RET|OOS|SHR}/{ID}.yaml`
- gold는 `{file_path, heading_path}` 쌍이고 heading_path 깊이는 2 이하다(§2.6).
  적중 판정 `GoldSection.matches`는 evaluation.md §2.1 `match(c, g)` 정의를 따른다.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

QUESTIONS_DIR = Path(__file__).resolve().parents[3] / "eval" / "questions"

VersionLabel = Literal["v0.3", "v1.x"]
QuestionType = Literal[
    "VERSION_SPECIFIC", "API_USAGE", "MIGRATION", "CONCEPT", "CODE_PATTERN", "OUT_OF_SCOPE"
]
Difficulty = Literal["EASY", "MEDIUM", "HARD"]

# 버전 표기 → 소스 키 (eval-scenarios.md §2.2, 정책서 §3.1 카탈로그)
VERSION_SOURCE_KEYS: dict[VersionLabel, str] = {
    "v0.3": "langchain_v03",
    "v1.x": "langchain_v1x",
}

# 셋 접두사 → (디렉터리, question_set 값)
SET_PREFIXES: dict[str, str] = {"RET": "Q-ret", "OOS": "Q-oos", "SHR": "Q-shared"}

# v1 구성 (eval-scenarios.md §1·§2.6)
V1_COUNTS: dict[str, int] = {"Q-ret": 40, "Q-oos": 10, "Q-shared": 20}
V1_RET_PER_VERSION = 20
V1_DECOYS_PER_VERSION = 5

MAX_GOLD_DEPTH = 2
_HEADING_SEP = " > "

NonEmpty = Annotated[str, Field(min_length=1)]


class QuestionSetError(ValueError):
    """질문셋 파일이 스키마·ID 규칙을 어김. 메시지에 파일 경로를 담는다."""


def _normalize(heading_path: str) -> str:
    return heading_path.strip().casefold()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GoldSection(_Strict):
    file_path: NonEmpty
    heading_path: NonEmpty

    @field_validator("heading_path")
    @classmethod
    def _depth_at_most_two(cls, value: str) -> str:
        if value.count(_HEADING_SEP) + 1 > MAX_GOLD_DEPTH:
            raise ValueError(f"gold heading_path 깊이는 {MAX_GOLD_DEPTH} 이하여야 합니다: {value}")
        return value

    def matches(self, file_path: str, heading_path: str) -> bool:
        """같은 파일이고 heading_path가 gold와 같거나 그 하위 섹션이면 적중."""
        if file_path != self.file_path:
            return False
        gold = _normalize(self.heading_path)
        chunk = _normalize(heading_path)
        return chunk == gold or chunk.startswith(gold + _HEADING_SEP.casefold())


class Metadata(_Strict):
    created_by: NonEmpty
    created_at: NonEmpty
    is_decoy: bool = False
    reviewed_by: str | None = None
    source: str | None = None


class Gold(_Strict):
    sections: list[GoldSection] = Field(min_length=1)
    note: str | None = None


class ExpectedBehavior(_Strict):
    no_context: bool
    reason: NonEmpty
    # false면 NO_CONTEXT 임계값 τ 결정(E1 부속) 표본에서 뺀다 — 범위 밖이 아니라 모호한 질문 등
    tau_calibration: bool = True


class _QuestionBase(_Strict):
    question_id: NonEmpty
    title: NonEmpty
    type: QuestionType
    difficulty: Difficulty
    query: NonEmpty
    metadata: Metadata


class RetQuestion(_QuestionBase):
    question_set: Literal["Q-ret"]
    target_version: VersionLabel
    gold: Gold

    @property
    def source_key(self) -> str:
        return VERSION_SOURCE_KEYS[self.target_version]


class OosQuestion(_QuestionBase):
    question_set: Literal["Q-oos"]
    type: Literal["OUT_OF_SCOPE"]
    target_version: None = None
    expected_behavior: ExpectedBehavior


class SharedVersion(_Strict):
    source_key: NonEmpty
    gold_sections: list[GoldSection] = Field(min_length=1)


class SharedVersions(_Strict):
    v0_3: SharedVersion
    v1_x: SharedVersion

    def by_label(self) -> dict[VersionLabel, SharedVersion]:
        return {"v0.3": self.v0_3, "v1.x": self.v1_x}


class SharedQuestion(_QuestionBase):
    question_set: Literal["Q-shared"]
    versions: SharedVersions
    label_schema: dict[str, str] = Field(min_length=1)

    @field_validator("versions")
    @classmethod
    def _source_keys_match_versions(cls, value: SharedVersions) -> SharedVersions:
        for label, version in value.by_label().items():
            if version.source_key != VERSION_SOURCE_KEYS[label]:
                raise ValueError(f"{label} source_key는 {VERSION_SOURCE_KEYS[label]}이어야 합니다")
        return value


Question = RetQuestion | OosQuestion | SharedQuestion
_MODELS: dict[str, type[RetQuestion] | type[OosQuestion] | type[SharedQuestion]] = {
    "Q-ret": RetQuestion,
    "Q-oos": OosQuestion,
    "Q-shared": SharedQuestion,
}


def load_question(path: Path) -> Question:
    """YAML 1개를 읽어 스키마를 검증한다. ID·디렉터리·파일명이 서로 맞아야 한다."""
    prefix = path.parent.name
    if prefix not in SET_PREFIXES:
        raise QuestionSetError(f"{path}: 셋 디렉터리는 {sorted(SET_PREFIXES)} 중 하나여야 합니다")
    if not re.fullmatch(rf"{prefix}-\d{{3}}", path.stem):
        raise QuestionSetError(f"{path}: 파일명은 {prefix}-3자리 숫자여야 합니다")
    data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise QuestionSetError(f"{path}: YAML 최상위가 매핑이 아닙니다")
    expected_set = SET_PREFIXES[prefix]
    if data.get("question_set") != expected_set:
        raise QuestionSetError(f"{path}: question_set은 {expected_set}이어야 합니다")
    if data.get("question_id") != path.stem:
        raise QuestionSetError(f"{path}: question_id가 파일명과 다릅니다")
    try:
        return _MODELS[expected_set].model_validate(data)
    except ValidationError as exc:
        raise QuestionSetError(f"{path}: {exc}") from exc


@dataclass(frozen=True)
class QuestionSets:
    ret: list[RetQuestion] = field(default_factory=list)
    oos: list[OosQuestion] = field(default_factory=list)
    shared: list[SharedQuestion] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {"Q-ret": len(self.ret), "Q-oos": len(self.oos), "Q-shared": len(self.shared)}


def load_question_sets(root: Path = QUESTIONS_DIR) -> QuestionSets:
    """`root/{RET,OOS,SHR}/*.yaml`을 ID 순으로 읽는다. 없는 셋은 빈 목록."""
    ret: list[RetQuestion] = []
    oos: list[OosQuestion] = []
    shared: list[SharedQuestion] = []
    for prefix in SET_PREFIXES:
        for path in sorted((root / prefix).glob("*.yaml")):
            question = load_question(path)
            if isinstance(question, RetQuestion):
                ret.append(question)
            elif isinstance(question, OosQuestion):
                oos.append(question)
            else:
                shared.append(question)
    return QuestionSets(ret=ret, oos=oos, shared=shared)


def v1_composition_errors(sets: QuestionSets) -> list[str]:
    """v1 구성(셋별 문항 수, Q-ret 버전·디코이 배분) 위반 목록. 빈 목록이면 통과."""
    errors = [
        f"{name} 문항 수 {actual} (기대 {V1_COUNTS[name]})"
        for name, actual in sets.counts().items()
        if actual != V1_COUNTS[name]
    ]
    for label in VERSION_SOURCE_KEYS:
        in_version = [q for q in sets.ret if q.target_version == label]
        decoys = [q for q in in_version if q.metadata.is_decoy]
        if len(in_version) != V1_RET_PER_VERSION:
            errors.append(f"Q-ret {label} {len(in_version)}문항 (기대 {V1_RET_PER_VERSION})")
        if len(decoys) != V1_DECOYS_PER_VERSION:
            errors.append(f"Q-ret {label} 디코이 {len(decoys)}개 (기대 {V1_DECOYS_PER_VERSION})")
    return errors


def tau_calibration_oos(sets: QuestionSets) -> list[OosQuestion]:
    """τ 결정 표본으로 쓰는 Q-oos 문항 (`expected_behavior.tau_calibration`이 true)."""
    return [q for q in sets.oos if q.expected_behavior.tau_calibration]


def unreviewed(sets: QuestionSets) -> list[str]:
    """사람 검수(`metadata.reviewed_by`)가 비어 있는 문항 ID — `eval-v1` 태그 전 0이어야 한다."""
    questions: list[Question] = [*sets.ret, *sets.oos, *sets.shared]
    return [q.question_id for q in questions if not q.metadata.reviewed_by]
