"""평가 질문셋 로더·스키마 검증 (eval-scenarios.md §2·§3, evaluation.md §2.1)."""

from pathlib import Path

import pytest
import yaml

from src.eval.questions import (
    GoldSection,
    OosQuestion,
    QuestionSetError,
    QuestionSets,
    RetQuestion,
    SharedQuestion,
    load_question,
    load_question_sets,
    tau_calibration_oos,
    unreviewed,
    v1_composition_errors,
)

META = {"created_by": "tester", "created_at": "2026-11-17T00:00:00Z"}


def _ret(qid: str = "RET-001", **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "question_id": qid,
        "question_set": "Q-ret",
        "title": "툴 정의",
        "type": "API_USAGE",
        "difficulty": "EASY",
        "target_version": "v1.x",
        "query": "툴을 정의하는 방법은?",
        "gold": {
            "sections": [
                {"file_path": "src/oss/langchain/tools.mdx", "heading_path": "Tools > Create tools"}
            ]
        },
        "metadata": dict(META),
    }
    data.update(overrides)
    return data


def _oos(qid: str = "OOS-001") -> dict[str, object]:
    return {
        "question_id": qid,
        "question_set": "Q-oos",
        "title": "범위 밖",
        "type": "OUT_OF_SCOPE",
        "difficulty": "EASY",
        "target_version": None,
        "query": "Django ORM 사용법은?",
        "expected_behavior": {"no_context": True, "reason": "LangChain 문서 밖"},
        "metadata": dict(META),
    }


def _shr(qid: str = "SHR-001", v1_source_key: str = "langchain_v1x") -> dict[str, object]:
    return {
        "question_id": qid,
        "question_set": "Q-shared",
        "title": "에이전트 생성",
        "type": "VERSION_SPECIFIC",
        "difficulty": "HARD",
        "query": "에이전트를 만드는 방법은?",
        "versions": {
            "v0_3": {
                "source_key": "langchain_v03",
                "gold_sections": [{"file_path": "a.ipynb", "heading_path": "Agents"}],
            },
            "v1_x": {
                "source_key": v1_source_key,
                "gold_sections": [{"file_path": "b.mdx", "heading_path": "Agents > Core"}],
            },
        },
        "label_schema": {"version_error": "0/1"},
        "metadata": dict(META),
    }


def _write(root: Path, prefix: str, data: dict[str, object], name: str | None = None) -> Path:
    path = root / prefix / f"{name or data['question_id']}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_loads_each_question_set(tmp_path: Path) -> None:
    _write(tmp_path, "RET", _ret())
    _write(tmp_path, "OOS", _oos())
    _write(tmp_path, "SHR", _shr())

    sets = load_question_sets(tmp_path)

    assert isinstance(sets.ret[0], RetQuestion)
    assert sets.ret[0].source_key == "langchain_v1x"
    assert isinstance(sets.oos[0], OosQuestion)
    assert isinstance(sets.shared[0], SharedQuestion)
    assert sets.counts() == {"Q-ret": 1, "Q-oos": 1, "Q-shared": 1}


def test_missing_set_directory_is_empty(tmp_path: Path) -> None:
    assert load_question_sets(tmp_path).counts() == {"Q-ret": 0, "Q-oos": 0, "Q-shared": 0}


@pytest.mark.parametrize(
    ("prefix", "data", "name", "message"),
    [
        ("XYZ", _ret(), None, "셋 디렉터리"),
        ("RET", _ret(), "RET-1", "파일명"),
        ("RET", _ret("RET-002"), "RET-001", "question_id가 파일명과"),
        ("OOS", _ret("OOS-001"), None, "question_set은 Q-oos"),
        ("RET", _ret(target_version=None), None, "target_version"),
        ("RET", _ret(extra_field=1), None, "extra_field"),
        ("RET", _ret(gold={"sections": []}), None, "sections"),
        ("SHR", _shr(v1_source_key="langchain_v03"), None, "source_key"),
    ],
)
def test_rejects_invalid_files(
    tmp_path: Path, prefix: str, data: dict[str, object], name: str | None, message: str
) -> None:
    path = _write(tmp_path, prefix, data, name)

    with pytest.raises(QuestionSetError, match=message):
        load_question(path)


def test_gold_heading_depth_is_at_most_two() -> None:
    with pytest.raises(ValueError, match="깊이"):
        GoldSection(file_path="a.mdx", heading_path="Tools > Create tools > Basic")


@pytest.mark.parametrize(
    ("file_path", "heading_path", "expected"),
    [
        ("a.mdx", "Tools > Create tools", True),
        ("a.mdx", "  tools > CREATE TOOLS ", True),
        ("a.mdx", "Tools > Create tools > Basic tool definition", True),
        ("a.mdx", "Tools > Create toolsets", False),
        ("a.mdx", "Tools", False),
        ("b.mdx", "Tools > Create tools", False),
    ],
)
def test_gold_matches_same_file_and_section_or_descendant(
    file_path: str, heading_path: str, expected: bool
) -> None:
    gold = GoldSection(file_path="a.mdx", heading_path="Tools > Create tools")

    assert gold.matches(file_path, heading_path) is expected


def test_v1_composition_errors_report_counts_and_decoys() -> None:
    ret = [
        RetQuestion.model_validate(_ret(f"RET-{i:03d}", target_version="v0.3")) for i in range(2)
    ]

    errors = v1_composition_errors(QuestionSets(ret=ret))

    assert "Q-ret 문항 수 2 (기대 40)" in errors
    assert "Q-ret v0.3 2문항 (기대 20)" in errors
    assert "Q-ret v1.x 디코이 0개 (기대 5)" in errors


def test_unreviewed_lists_questions_without_reviewer() -> None:
    reviewed = _ret("RET-001", metadata={**META, "reviewed_by": "r1nn"})
    sets = QuestionSets(
        ret=[RetQuestion.model_validate(reviewed), RetQuestion.model_validate(_ret("RET-002"))],
        oos=[OosQuestion.model_validate(_oos())],
    )

    assert unreviewed(sets) == ["RET-002", "OOS-001"]


def test_tau_calibration_defaults_true_and_can_exclude_ambiguous_questions() -> None:
    ambiguous = _oos("OOS-002")
    ambiguous["expected_behavior"] = {
        "no_context": True,
        "reason": "모호함",
        "tau_calibration": False,
    }
    sets = QuestionSets(
        oos=[OosQuestion.model_validate(_oos()), OosQuestion.model_validate(ambiguous)]
    )

    assert sets.oos[0].expected_behavior.tau_calibration is True  # 필드가 없으면 포함
    assert [q.question_id for q in tau_calibration_oos(sets)] == ["OOS-001"]


def test_repository_question_sets_match_v1_composition() -> None:
    """저장소 `eval/questions/` 전체가 스키마와 v1 구성을 지킨다 (eval-scenarios.md §1·§2.6)."""
    sets = load_question_sets()

    assert v1_composition_errors(sets) == []
    golds = [s for q in sets.ret for s in q.gold.sections] + [
        s for q in sets.shared for v in q.versions.by_label().values() for s in v.gold_sections
    ]
    # 정책서 §3.2 제외 범위는 gold로 쓰지 않는다
    excluded = [
        g.file_path for g in golds if "integrations/" in g.file_path or "langgraph" in g.file_path
    ]
    assert excluded == []
