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
