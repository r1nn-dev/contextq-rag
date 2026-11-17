"""run별 산출 리포트 — `${INGEST_DATA_DIR}/reports/run{id}/` (data-sources.md §2)."""

import csv
import json
from pathlib import Path
from typing import Any

from src.adapters.base import MissingSnippet


def report_dir(data_dir: Path, run_id: int) -> Path:
    return data_dir / "reports" / f"run{run_id}"


def write_missing_snippets(directory: Path, missing: list[MissingSnippet]) -> Path:
    """정책서 §4.3 `missing_snippets.csv` — 누락이 없어도 헤더만 있는 파일을 남긴다."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "missing_snippets.csv"
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["file_path", "component", "import_path"])
        writer.writerows([m.file_path, m.component, m.import_path] for m in missing)
    return path


def write_json(directory: Path, name: str, payload: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
