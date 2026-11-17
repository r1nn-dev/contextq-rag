"""활성화·롤백 후 서버 포인터 reload 호출 — 정책서 §4.5 "반영", api-spec.md §6.5.

호출이 실패해도 명령은 성공이다. ai-server의 포인터 캐시(30초)가 만료되면 새 run이 반영된다.
"""

from typing import Any

import httpx

RELOAD_PATH = "/internal/v1/index/reload"
RELOAD_TIMEOUT_SECONDS = 3.0  # 내부망 호출 — 3초를 넘으면 장애로 본다 (정책서 §2.1 WebClient 연결)


def notify_reload(base_url: str, token: str, source_key: str, *, client: Any = None) -> str | None:
    """성공하면 None, 실패하면 이유(경고 문구)를 돌려준다. 예외를 던지지 않는다."""
    http = client or httpx.Client(timeout=RELOAD_TIMEOUT_SECONDS)
    try:
        response = http.post(
            base_url.rstrip("/") + RELOAD_PATH,
            json={"sourceKey": source_key},
            headers={"X-Internal-Token": token},
        )
    except httpx.HTTPError as exc:
        return f"{type(exc).__name__}: {exc}"
    finally:
        if client is None:
            http.close()
    if response.status_code != 200:
        try:
            code = response.json().get("code", "")
        except ValueError:
            code = ""
        return f"HTTP {response.status_code} {code}".strip()
    return None
