"""`.ipynb` 직렬화 — doc-source.md §4.3.

셀 순서대로 markdown·raw 셀은 원문, code 셀은 ```python 펜스로 감싸 빈 줄로 잇는다.
출력 셀(outputs)은 넣지 않는다. 반환 텍스트의 줄 번호가 노트북 문서의 라인 번호다.
"""

import json
from typing import Any


class NotebookFormatError(ValueError):
    """JSON이 아니거나 cells가 없는 노트북."""


def _source(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    text = "".join(source) if isinstance(source, list) else str(source)
    return text.replace("\r\n", "\n").strip("\n")


def serialize_notebook(raw: str) -> str:
    try:
        notebook = json.loads(raw)
        cells = notebook["cells"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise NotebookFormatError(f"노트북 형식이 아닙니다: {exc}") from exc

    blocks: list[str] = []
    for cell in cells:
        text = _source(cell)
        if not text.strip():
            continue
        if cell.get("cell_type") == "code":
            blocks.append(f"```python\n{text}\n```")
        else:  # markdown, raw — 첫 raw 셀의 frontmatter는 문서 첫 줄이 되어 그대로 처리된다
            blocks.append(text)
    return "\n\n".join(blocks)
