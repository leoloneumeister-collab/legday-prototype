"""Shared plumbing for data sources.

The contract: a source never raises at the caller. It returns a SourceResult that
is either ok with data, or not ok with an error string. A missing news feed should
degrade the brief, not cancel it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

USER_AGENT = "jarvis-brief/0.1 (personal portfolio brief)"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))

    @property
    def rate_limit(self) -> dict[str, str]:
        """The x-ratelimit-* headers Trading212 returns, for `doctor` to show."""
        return {
            k.lower(): v
            for k, v in self.headers.items()
            if k.lower().startswith("x-ratelimit")
        }


class HttpError(Exception):
    def __init__(self, status: int, message: str, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def http_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 30.0,
) -> HttpResponse:
    """One small urllib wrapper so every source reports failures the same way."""
    req = urllib.request.Request(url, method=method, data=body)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(resp.status, dict(resp.headers.items()), resp.read())
    except urllib.error.HTTPError as exc:  # 4xx/5xx carry a useful body
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:500]
        except Exception:  # pragma: no cover - body already consumed
            pass
        raise HttpError(exc.code, f"HTTP {exc.code} {exc.reason}", detail) from exc
    except urllib.error.URLError as exc:
        raise HttpError(0, f"connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise HttpError(0, f"timed out after {timeout}s") from exc


@dataclass
class SourceResult:
    """What every source hands back. `ok=False` is a normal, expected outcome."""

    name: str
    ok: bool
    data: Any = None
    error: str | None = None
    fetched_at: str = field(default_factory=utc_now_iso)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, name: str, data: Any, **kw: Any) -> "SourceResult":
        return cls(name=name, ok=True, data=data, **kw)

    @classmethod
    def failure(cls, name: str, error: str, **kw: Any) -> "SourceResult":
        return cls(name=name, ok=False, error=error, **kw)


class RateLimiter:
    """Minimum spacing between calls, per endpoint.

    Trading212 allows bursts, but its per-endpoint limits are as tight as 1 req/s
    and a 429 wastes the whole run, so we simply never go faster than the limit.
    """

    def __init__(self, sleep: Callable[[float], None] = time.sleep) -> None:
        self._last: dict[str, float] = {}
        self._sleep = sleep

    def wait(self, key: str, min_interval: float, now: Callable[[], float] = time.monotonic) -> None:
        last = self._last.get(key)
        current = now()
        if last is not None:
            remaining = min_interval - (current - last)
            if remaining > 0:
                self._sleep(remaining)
                current = now()
        self._last[key] = current


def first_present(obj: dict[str, Any], *names: str, default: Any = None) -> Any:
    """Read the first key that exists and is not None.

    Every external payload in here is read through this: the Trading212 schema
    already renamed fields once (`ppl` -> `walletImpact.unrealizedProfitLoss`), and
    Finlight's article shape is undocumented, so tolerating both spellings is
    cheaper than a broken morning.
    """
    for name in names:
        if name in obj and obj[name] is not None:
            return obj[name]
    return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
