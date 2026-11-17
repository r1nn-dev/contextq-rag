"""COLLECTING 단계 — 카탈로그 값으로 git sparse checkout을 실행하고 커밋 SHA를 얻는다.

- 수집 대상(저장소·ref·문서 경로)은 `ai.sources`에서 읽는다 (ADR-006).
- 매 run 새로 받는다. 이전 run 파일이 섞이면 SHA와 내용이 어긋나기 때문이다.
- 체크아웃 결과에 `SOURCE.txt`(repo, ref, sha, 수집 시각)를 남긴다 (data-sources.md §2).
"""

import os
import re
import shutil
import stat
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.domain.tables import Source

GITHUB = "https://github.com"
SOURCE_FILE = "SOURCE.txt"
GIT_TIMEOUT_SECONDS = 600
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

# 포맷별로 문서 경로 외에 함께 받아야 하는 경로 (data-sources.md §3.2 체크아웃 경로)
EXTRA_CHECKOUT_PATHS: dict[str, tuple[str, ...]] = {
    "MINTLIFY": ("src/snippets/",),  # 스니펫 인라인 확장 원본 (정책서 §4.3)
}


class CollectError(RuntimeError):
    """체크아웃 실패 — run을 FAILED(COLLECTING)로 만든다."""


@dataclass(frozen=True)
class CheckoutSpec:
    repo: str  # "owner/name"
    ref: str  # 브랜치 또는 태그
    paths: tuple[str, ...]  # 저장소 루트 기준 디렉터리


@dataclass(frozen=True)
class CheckoutResult:
    root: Path
    commit_sha: str


def checkout_spec(source: Source) -> CheckoutSpec:
    paths = (source.doc_path, *EXTRA_CHECKOUT_PATHS.get(source.doc_format, ()))
    return CheckoutSpec(repo=source.repo_url, ref=source.ref, paths=paths)


def _git(*args: str, cwd: Path | None = None) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # 인증 프롬프트로 멈추지 않게
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip().splitlines()[-3:]
        raise CollectError(f"git {args[0]} 실패: {' | '.join(detail)}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CollectError(f"git {args[0]} 제한 시간({GIT_TIMEOUT_SECONDS}s) 초과") from exc
    return completed.stdout.strip()


def _force_remove(func: Callable[..., Any], path: str, _exc: BaseException) -> None:
    # Windows에서 git pack 파일은 읽기 전용이라 권한을 풀고 다시 지운다
    os.chmod(path, stat.S_IWRITE)
    func(path)


def sparse_checkout(spec: CheckoutSpec, dest: Path, *, remote_base: str = GITHUB) -> CheckoutResult:
    """dest를 비우고 spec.paths만 체크아웃한 뒤 HEAD 커밋 SHA를 돌려준다."""
    if dest.exists():
        shutil.rmtree(dest, onexc=_force_remove)
    dest.parent.mkdir(parents=True, exist_ok=True)

    url = f"{remote_base}/{spec.repo}.git"
    _git(
        "clone",
        "--quiet",
        "--filter=blob:none",
        "--no-checkout",
        "--depth",
        "1",
        "--branch",
        spec.ref,
        url,
        str(dest),
    )
    _git("sparse-checkout", "set", *(p.strip("/") for p in spec.paths), cwd=dest)
    _git("checkout", "--quiet", cwd=dest)

    sha = _git("rev-parse", "HEAD", cwd=dest)
    if not _SHA_PATTERN.match(sha):
        raise CollectError(f"커밋 SHA 형식이 아닙니다: {sha!r}")
    missing = [p for p in spec.paths if not (dest / p).is_dir()]
    if missing:
        raise CollectError(f"체크아웃 결과에 경로가 없습니다: {', '.join(missing)}")

    collected_at = datetime.now(UTC).isoformat(timespec="seconds")
    (dest / SOURCE_FILE).write_text(
        f"repo={spec.repo}\nref={spec.ref}\nsha={sha}\ncollected_at={collected_at}\n",
        encoding="utf-8",
    )
    return CheckoutResult(root=dest, commit_sha=sha)
