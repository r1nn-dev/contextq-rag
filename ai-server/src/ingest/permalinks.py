"""permalink 전수 검증 — 정책서 §4.4, ADR-007.

- 라인 앵커(`?plain=1#L…`)를 떼고 파일 단위로 중복을 제거한 URL 전부에 요청한다.
- 초당 5건으로 제한하고, `GITHUB_TOKEN`이 있으면 인증 헤더를 붙인다.
- 상태 코드는 정확히 200이어야 한다(리다이렉트는 실패로 본다 — SHA 고정 URL은 이동하지 않는다).
"""

import time
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

import httpx

from src.ingest.validate import MAX_EXAMPLES, CheckResult, Deadline

REQUESTS_PER_SECOND = 5
REQUEST_TIMEOUT_SECONDS = 15


def file_url(permalink: str) -> str:
    parts = urlsplit(permalink)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def unique_file_urls(permalinks: Iterable[str]) -> list[str]:
    return sorted({file_url(p) for p in permalinks if p})


class PermalinkChecker:
    def __init__(
        self,
        client: httpx.Client,
        *,
        token: str = "",
        rate_per_second: float = REQUESTS_PER_SECOND,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.interval = 1.0 / rate_per_second
        self.sleep = sleep
        self.clock = clock

    @classmethod
    def create(cls, token: str = "") -> "PermalinkChecker":
        client = httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False)
        return cls(client, token=token)

    def _status(self, url: str) -> int | str:
        try:
            response = self.client.head(url, headers=self.headers)
            if response.status_code == 405:  # HEAD 미지원이면 GET으로 다시 확인
                response = self.client.get(url, headers=self.headers)
            return response.status_code
        except httpx.HTTPError as exc:
            return type(exc).__name__

    def check(self, permalinks: Iterable[str], deadline: Deadline) -> CheckResult:
        urls = unique_file_urls(permalinks)
        failures: list[str] = []
        last_start: float | None = None
        for url in urls:
            deadline.check()
            if last_start is not None:
                wait = self.interval - (self.clock() - last_start)
                if wait > 0:
                    self.sleep(wait)
            last_start = self.clock()
            status = self._status(url)
            if status != 200:
                failures.append(f"{status} {url}")
        return CheckResult(
            "permalink",
            bool(urls) and not failures,
            {
                "unique_files": len(urls),
                "failed": len(failures),
                "examples": failures[:MAX_EXAMPLES],
                "authenticated": bool(self.headers),
            },
        )
