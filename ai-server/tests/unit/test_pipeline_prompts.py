"""단일 모드 프롬프트 v1과 생성 설정 — 정책서 §5.1·§5.5, rag-pipeline.md §3.5."""

from pathlib import Path

import pytest

from src.config.rag_config import load_llm_config
from src.config.settings import Settings
from src.domain.retrieval import RetrievedChunk
from src.pipeline.prompts import (
    NO_ANSWER_SENTINEL,
    PROMPTS_DIR,
    PromptNotFoundError,
    build_messages,
    version_header,
)


def chunk(heading: str, content: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=heading,
        content=content,
        permalink="",
        source_key="langchain_v1x",
        file_path="src/oss/langchain/agents.mdx",
        heading_path=heading,
        token_count=10,
        site_url="",
        similarity=0.8,
    )


def test_single_v1_numbers_documents_in_rank_order() -> None:
    messages = build_messages(
        "single_v1",
        display_name="LangChain v1.x",
        question="에이전트는 어떻게 만드나요?",
        chunks=[chunk("Agents > Create", "Use create_agent."), chunk("Agents > Tools", "Tools.")],
    )

    system, user = messages
    assert user == {"role": "user", "content": "에이전트는 어떻게 만드나요?"}
    text = system["content"]
    assert system["role"] == "system"
    assert text.index("[1] Agents > Create (src/oss/langchain/agents.mdx)") < text.index(
        "[2] Agents > Tools"
    )
    assert "Use create_agent." in text


def test_single_v1_carries_the_five_policy_rules() -> None:
    [system, _] = build_messages(
        "single_v1", display_name="LangChain v0.3", question="q", chunks=[]
    )
    text = system["content"]

    assert "[참고 문서]에 없는 지식" in text  # ① 컨텍스트 밖 지식 금지
    assert "[n] 형식" in text  # ② 인용
    assert '"LangChain v0.3 기준"' in text  # ③ 첫 줄 버전 명시
    assert "코드 예시는 [참고 문서]의 코드에 근거" in text  # ④ 코드 근거
    assert f"{NO_ANSWER_SENTINEL} 만 출력" in text  # ⑤ sentinel
    assert "한국어" in text  # 정책서 §5.1 답변 언어


def test_single_v2_puts_sentinel_rule_above_version_header() -> None:
    """#108: 근거 부족이면 기준 버전 줄 없이 sentinel만 (규칙 ⑤가 ③보다 우선)."""
    [system, _] = build_messages(
        "single_v2", display_name="LangChain v1.x", question="q", chunks=[]
    )
    text = system["content"]

    assert '답할 수 있으면 답변 첫 줄에 "LangChain v1.x 기준"' in text  # ③ 조건부
    assert f'"LangChain v1.x 기준" 줄도 쓰지 말고 다른 말 없이 {NO_ANSWER_SENTINEL} 만 출력' in text
    assert "규칙 3보다 우선" in text
    assert "[n] 형식" in text and "코드 예시는 [참고 문서]의 코드에 근거" in text


def test_version_header_is_shared_by_prompt_and_gate() -> None:
    assert version_header("LangChain v0.3") == "LangChain v0.3 기준"


@pytest.mark.parametrize("version", ["single_v9", "../models", "Single_V1", ""])
def test_unknown_or_unsafe_version_is_rejected(version: str) -> None:
    with pytest.raises(PromptNotFoundError):
        build_messages(version, display_name="x", question="q", chunks=[])


def test_template_variables_are_strict(tmp_path: Path) -> None:
    (tmp_path / "single_v1.j2").write_text("{{ missing }}", encoding="utf-8")

    with pytest.raises(Exception, match="missing"):
        build_messages("single_v1", display_name="x", question="q", chunks=[], prompts_dir=tmp_path)


def test_prompt_files_are_versioned_by_name() -> None:
    assert (PROMPTS_DIR / "single_v1.j2").is_file()  # 이전 버전 파일은 지우지 않는다 (정책서 §5.5)
    assert (PROMPTS_DIR / "single_v2.j2").is_file()


def test_llm_config_matches_policy() -> None:
    llm = load_llm_config()

    assert (llm.model, llm.temperature, llm.max_tokens) == ("gpt-4o-mini", 0, 1024)
    assert (llm.first_token_timeout_seconds, llm.max_retries) == (10, 0)


def test_llm_model_env_override() -> None:
    llm = load_llm_config()
    settings = Settings(_env_file=None, llm_model="gpt-4o-2024-08-06")  # type: ignore[call-arg]

    assert llm.resolve_model(settings.llm_model) == "gpt-4o-2024-08-06"
    assert llm.resolve_model("") == "gpt-4o-mini"
