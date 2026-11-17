"""permalink 전수 검증 — 파일 단위 중복 제거, 200만 통과, 초당 5건, 토큰 헤더 (네트워크 없음)."""

import httpx
import pytest

from src.ingest.permalinks import PermalinkChecker, file_url, unique_file_urls
from src.ingest.validate import Deadline, ValidationTimeoutError

SHA = "a" * 40
BASE = f"https://github.com/o/r/blob/{SHA}"


def _checker(statuses: dict[str, int], seen: list[httpx.Request], **kw: object) -> PermalinkChecker:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        status = statuses.get(str(request.url), 200)
        if request.method == "HEAD" and status == 405:
            return httpx.Response(405)
        return httpx.Response(200 if status == 405 else status)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PermalinkChecker(client, **kw)  # type: ignore[arg-type]


def test_file_url_strips_line_anchor() -> None:
    assert file_url(f"{BASE}/a.mdx?plain=1#L1-L9") == f"{BASE}/a.mdx"


def test_unique_files_only() -> None:
    links = [f"{BASE}/a.mdx?plain=1#L1-L9", f"{BASE}/a.mdx?plain=1#L10-L20", f"{BASE}/b.ipynb", ""]
    assert unique_file_urls(links) == [f"{BASE}/a.mdx", f"{BASE}/b.ipynb"]


def test_all_200_passes_with_token_header() -> None:
    seen: list[httpx.Request] = []
    result = _checker({}, seen, token="t0k", sleep=lambda s: None).check(
        [f"{BASE}/a.mdx?plain=1#L1-L2", f"{BASE}/b.mdx"], Deadline.after(60)
    )
    assert result.passed and result.detail["unique_files"] == 2
    assert all(r.headers["Authorization"] == "Bearer t0k" for r in seen)
    assert {r.method for r in seen} == {"HEAD"}


def test_non_200_and_redirect_fail() -> None:
    statuses = {f"{BASE}/gone.mdx": 404, f"{BASE}/moved.mdx": 301}
    result = _checker(statuses, [], sleep=lambda s: None).check(
        [f"{BASE}/ok.mdx", f"{BASE}/gone.mdx", f"{BASE}/moved.mdx"], Deadline.after(60)
    )
    assert not result.passed
    assert result.detail["failed"] == 2


def test_head_not_allowed_falls_back_to_get() -> None:
    seen: list[httpx.Request] = []
    result = _checker({f"{BASE}/a.mdx": 405}, seen, sleep=lambda s: None).check(
        [f"{BASE}/a.mdx"], Deadline.after(60)
    )
    assert result.passed
    assert [r.method for r in seen] == ["HEAD", "GET"]


def test_rate_limited_to_five_per_second() -> None:
    sleeps: list[float] = []
    now = [0.0]
    checker = _checker({}, [], sleep=sleeps.append, clock=lambda: now[0])
    checker.check([f"{BASE}/{i}.mdx" for i in range(3)], Deadline.after(60))
    assert sleeps == pytest.approx([0.2, 0.2])


def test_no_permalinks_fails() -> None:
    assert not _checker({}, [], sleep=lambda s: None).check([], Deadline.after(60)).passed


def test_deadline_stops_checking() -> None:
    with pytest.raises(ValidationTimeoutError):
        _checker({}, [], sleep=lambda s: None).check([f"{BASE}/a.mdx"], Deadline.after(-1))
