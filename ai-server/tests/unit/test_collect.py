"""sparse checkout — 로컬 git 저장소(file://)로 네트워크 없이 확인한다."""

import subprocess
from pathlib import Path

import pytest

from src.domain.tables import Source
from src.ingest.collect import CheckoutSpec, CollectError, checkout_spec, sparse_checkout


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture()
def remote(tmp_path: Path) -> tuple[str, str]:
    """owner/docs 저장소를 만들고 (remote_base, 커밋 SHA)를 돌려준다."""
    repo = tmp_path / "remote" / "owner" / "docs.git"
    for rel in ["src/oss/a.mdx", "src/oss/sub/b.mdx", "src/snippets/s.mdx", "other/x.md"]:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(f"# {rel}\n", encoding="utf-8")
    _git(repo, "init", "--quiet", "--initial-branch", "main")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "init")
    _git(repo, "tag", "v0.3")
    return (tmp_path / "remote").as_uri(), _git(repo, "rev-parse", "HEAD")


def _source(doc_format: str) -> Source:
    return Source(
        source_key="k",
        repo_url="owner/docs",
        ref="main",
        doc_path="src/oss/",
        doc_format=doc_format,
    )


def test_checkout_spec_adds_snippets_for_mintlify() -> None:
    assert checkout_spec(_source("MINTLIFY")).paths == ("src/oss/", "src/snippets/")
    assert checkout_spec(_source("DOCUSAURUS")).paths == ("src/oss/",)


@pytest.mark.parametrize("ref", ["main", "v0.3"])
def test_sparse_checkout_records_sha_and_limits_paths(
    tmp_path: Path, remote: tuple[str, str], ref: str
) -> None:
    base, sha = remote
    spec = CheckoutSpec(repo="owner/docs", ref=ref, paths=("src/oss/", "src/snippets/"))
    result = sparse_checkout(spec, tmp_path / "raw" / "k", remote_base=base)

    assert result.commit_sha == sha
    assert (result.root / "src/oss/sub/b.mdx").is_file()
    assert (result.root / "src/snippets/s.mdx").is_file()
    assert not (result.root / "other").exists()
    source_txt = (result.root / "SOURCE.txt").read_text(encoding="utf-8")
    assert f"sha={sha}" in source_txt
    assert "repo=owner/docs" in source_txt


def test_sparse_checkout_replaces_previous_run(tmp_path: Path, remote: tuple[str, str]) -> None:
    base, _ = remote
    dest = tmp_path / "raw" / "k"
    dest.mkdir(parents=True)
    (dest / "stale.mdx").write_text("old", encoding="utf-8")

    sparse_checkout(CheckoutSpec("owner/docs", "main", ("src/oss/",)), dest, remote_base=base)
    assert not (dest / "stale.mdx").exists()


def test_unknown_ref_raises_collect_error(tmp_path: Path, remote: tuple[str, str]) -> None:
    base, _ = remote
    with pytest.raises(CollectError, match="clone"):
        sparse_checkout(
            CheckoutSpec("owner/docs", "no-such-ref", ("src/oss/",)),
            tmp_path / "raw" / "k",
            remote_base=base,
        )


def test_missing_doc_path_raises_collect_error(tmp_path: Path, remote: tuple[str, str]) -> None:
    base, _ = remote
    with pytest.raises(CollectError, match="docs/docs/"):
        sparse_checkout(
            CheckoutSpec("owner/docs", "main", ("docs/docs/",)),
            tmp_path / "raw" / "k",
            remote_base=base,
        )


# --- 커밋 고정 (#144) -----------------------------------------------------------


@pytest.fixture()
def history(tmp_path: Path) -> tuple[str, str, str, str]:
    """main 커밋 2개 + 다른 브랜치 커밋 1개 → (remote_base, 첫·최신 커밋, 다른 브랜치 커밋)."""
    repo = tmp_path / "remote" / "owner" / "docs.git"
    page = repo / "src/oss/a.mdx"
    page.parent.mkdir(parents=True)
    commit = ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm"]
    page.write_text("# v1\n", encoding="utf-8")
    _git(repo, "init", "--quiet", "--initial-branch", "main")
    _git(repo, "add", ".")
    _git(repo, *commit, "one")
    first = _git(repo, "rev-parse", "HEAD")
    _git(repo, "switch", "--quiet", "-c", "side")
    page.write_text("# side\n", encoding="utf-8")
    _git(repo, *commit, "side", "-a")
    side = _git(repo, "rev-parse", "HEAD")
    _git(repo, "switch", "--quiet", "main")
    page.write_text("# v2\n", encoding="utf-8")
    _git(repo, *commit, "two", "-a")
    return (tmp_path / "remote").as_uri(), first, _git(repo, "rev-parse", "HEAD"), side


def test_pinned_commit_checks_out_that_commit(
    tmp_path: Path, history: tuple[str, str, str, str]
) -> None:
    base, first, latest, _ = history
    spec = CheckoutSpec("owner/docs", "main", ("src/oss/",), commit=first)

    result = sparse_checkout(spec, tmp_path / "raw" / "k", remote_base=base)

    assert result.commit_sha == first != latest
    assert (result.root / "src/oss/a.mdx").read_text(encoding="utf-8") == "# v1\n"
    assert f"sha={first}" in (result.root / "SOURCE.txt").read_text(encoding="utf-8")


def test_unpinned_checkout_still_takes_the_latest_commit(
    tmp_path: Path, history: tuple[str, str, str, str]
) -> None:
    base, _, latest, _ = history
    spec = CheckoutSpec("owner/docs", "main", ("src/oss/",))

    assert sparse_checkout(spec, tmp_path / "raw" / "k", remote_base=base).commit_sha == latest


def test_commit_outside_the_ref_history_is_rejected(
    tmp_path: Path, history: tuple[str, str, str, str]
) -> None:
    base, _, _, side = history
    spec = CheckoutSpec("owner/docs", "main", ("src/oss/",), commit=side)

    with pytest.raises(CollectError, match="main 이력에 없습니다"):
        sparse_checkout(spec, tmp_path / "raw" / "k", remote_base=base)


def test_pinned_commit_must_be_a_full_sha(tmp_path: Path) -> None:
    spec = CheckoutSpec("owner/docs", "main", ("src/oss/",), commit="main")

    with pytest.raises(CollectError, match="40자"):
        sparse_checkout(spec, tmp_path / "raw" / "k", remote_base="file:///unused")
