"""생성 프롬프트 — `configs/prompts/{prompt_version}.j2` (정책서 §5.5·§5.6, rag-pipeline §3.5·§5).

- 파일명(확장자 제외)이 `prompt_version`이다. 문구 변경은 새 버전 파일로만 한다.
- 컨텍스트 번호(`rank`)가 인용 번호 [n]이고 SSE meta.sources rank와 같다(INV-08).
  비교 모드는 측마다 `A1…`·`B1…`이다(정책서 §5.6).
- 프롬프트 문구는 템플릿에만 둔다. 코드에는 변수만 있다 (CONTRIBUTING.md §9.5).
"""

import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template, TemplateNotFound

from src.config.ingest_config import CONFIG_DIR
from src.domain.retrieval import RetrievedChunk

PROMPTS_DIR = CONFIG_DIR / "prompts"
NO_ANSWER_SENTINEL = "[[NO_ANSWER]]"  # 근거 부족 선언 (정책서 §5.4 LLM_ABSTAIN)
VERSION_HEADER = "{display_name} 기준"  # 답변 첫 줄 기준 버전 (정책서 §5.5 ③). sentinel 판정도 쓴다
_VERSION = re.compile(r"^[a-z][a-z0-9_]*$")  # 요청 값으로 경로를 만들므로 형식을 제한한다


def version_header(display_name: str) -> str:
    return VERSION_HEADER.format(display_name=display_name)


class PromptNotFoundError(LookupError):
    """prompt_version에 해당하는 프롬프트 파일이 없음 (HTTP 400 INVALID_REQUEST)."""


@lru_cache
def _environment(prompts_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(prompts_dir),
        undefined=StrictUndefined,
        autoescape=False,  # 결과는 HTML이 아니라 LLM 입력 텍스트다
        keep_trailing_newline=False,
    )


def load_template(prompt_version: str, prompts_dir: Path = PROMPTS_DIR) -> Template:
    if not _VERSION.match(prompt_version):
        raise PromptNotFoundError(f"프롬프트 버전 형식이 올바르지 않습니다: {prompt_version!r}")
    try:
        return _environment(prompts_dir).get_template(f"{prompt_version}.j2")
    except TemplateNotFound:
        raise PromptNotFoundError(f"프롬프트 파일이 없습니다: {prompt_version}") from None


def build_messages(
    prompt_version: str,
    *,
    display_name: str,
    question: str,
    chunks: Sequence[RetrievedChunk],
    prompts_dir: Path = PROMPTS_DIR,
) -> list[dict[str, str]]:
    """system = 규칙 + 번호 붙은 [참고 문서], user = 질문 원문."""
    system = load_template(prompt_version, prompts_dir).render(
        display_name=display_name,
        header=version_header(display_name),
        documents=_documents(chunks),
        sentinel=NO_ANSWER_SENTINEL,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": question}]


def _documents(chunks: Sequence[RetrievedChunk], prefix: str = "") -> list[dict[str, object]]:
    return [
        {
            "rank": f"{prefix}{rank}",
            "heading_path": chunk["heading_path"],
            "file_path": chunk["file_path"],
            "content": chunk["content"],
        }
        for rank, chunk in enumerate(chunks, start=1)
    ]


def build_compare_messages(
    prompt_version: str,
    *,
    display_name_a: str,
    display_name_b: str,
    question: str,
    chunks_a: Sequence[RetrievedChunk],
    chunks_b: Sequence[RetrievedChunk],
    prompts_dir: Path = PROMPTS_DIR,
) -> list[dict[str, str]]:
    """비교 모드: system = 규칙 + [버전 A 문서](A1…)·[버전 B 문서](B1…), user = 질문 원문.

    근거가 없는 측은 빈 시퀀스로 넘긴다 — 템플릿이 "근거 문서 없음"을 적는다.
    """
    system = load_template(prompt_version, prompts_dir).render(
        display_name_a=display_name_a,
        display_name_b=display_name_b,
        documents_a=_documents(chunks_a, "A"),
        documents_b=_documents(chunks_b, "B"),
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": question}]
