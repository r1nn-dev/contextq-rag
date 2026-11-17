"""단일 모드 프롬프트 — `configs/prompts/{prompt_version}.j2` (정책서 §5.5, rag-pipeline.md §3.5).

- 파일명(확장자 제외)이 `prompt_version`이다. 문구 변경은 새 버전 파일로만 한다.
- 컨텍스트 번호(`rank`)가 인용 번호 [n]이고 SSE meta.sources rank와 같다(INV-08).
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
_VERSION = re.compile(r"^[a-z][a-z0-9_]*$")  # 요청 값으로 경로를 만들므로 형식을 제한한다


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
    documents = [
        {
            "rank": rank,
            "heading_path": chunk["heading_path"],
            "file_path": chunk["file_path"],
            "content": chunk["content"],
        }
        for rank, chunk in enumerate(chunks, start=1)
    ]
    system = load_template(prompt_version, prompts_dir).render(
        display_name=display_name, documents=documents, sentinel=NO_ANSWER_SENTINEL
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": question}]
