"""HTTP 会话与 JSON 请求辅助。"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def new_session(
    headers: dict | None = None,
    retries: int = 3,
    proxy: str = "",
    timeout: float = 20.0,
) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_UA})
    if headers:
        session.headers.update(headers)
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST", "HEAD"}),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.request_timeout = timeout  # type: ignore[attr-defined]
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    return session


def request(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", getattr(session, "request_timeout", 20.0))
    resp = session.request(method, url, **kwargs)
    resp.raise_for_status()
    return resp


def get_json(session: requests.Session, url: str, **kwargs) -> dict:
    return _json(request(session, "GET", url, **kwargs))


def post_json(session: requests.Session, url: str, **kwargs) -> dict:
    return _json(request(session, "POST", url, **kwargs))


def _json(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError(
            f"expected JSON from {resp.url}, got {resp.headers.get('Content-Type')!r}"
        ) from exc
