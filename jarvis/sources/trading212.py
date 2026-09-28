"""Trading212 public API — positions and account summary.

Endpoints and limits confirmed against the current (v0, beta) API surface:

    GET /api/v0/equity/positions          1 req / 1s   scope: portfolio
    GET /api/v0/equity/account/summary    1 req / 5s   scope: account

Auth is HTTP Basic with API_KEY as the username and API_SECRET as the password.
(An older raw `Authorization: <key>` header scheme also exists; if a key predates
the key/secret pair, set T212_API_SECRET empty and the legacy header is used.)

Values come back in the account's primary currency — the API does not support
multi-currency accounts, so no FX conversion happens here.
"""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .base import (
    HttpError,
    RateLimiter,
    SourceResult,
    as_float,
    first_present,
    http_request,
)

BASE_URLS = {
    "live": "https://live.trading212.com/api/v0",
    "demo": "https://demo.trading212.com/api/v0",
}

POSITIONS_PATH = "/equity/positions"
SUMMARY_PATH = "/equity/account/summary"

# Per-endpoint minimum spacing, from the documented limits above.
MIN_INTERVAL = {POSITIONS_PATH: 1.0, SUMMARY_PATH: 5.0}

SCOPE_HINTS = {
    POSITIONS_PATH: "the API key is missing the 'portfolio' scope",
    SUMMARY_PATH: "the API key is missing the 'account' scope",
}


@dataclass
class Position:
    ticker: str            # display form, e.g. AAPL
    raw_ticker: str        # as the API returns it, e.g. AAPL_US_EQ
    name: str
    currency: str
    quantity: float
    avg_price: float
    current_price: float
    value: float
    unrealized_pl: float
    isin: str = ""
    pct_of_portfolio: float = 0.0
    opened_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AccountSummary:
    currency: str = ""
    total_value: float = 0.0
    invested: float = 0.0
    current_value: float = 0.0
    unrealized_pl: float = 0.0
    realized_pl: float = 0.0
    cash_available: float = 0.0
    cash_in_pies: float = 0.0
    cash_reserved: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PortfolioSnapshotData:
    positions: list[Position] = field(default_factory=list)
    account: AccountSummary = field(default_factory=AccountSummary)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "positions": [p.to_dict() for p in self.positions],
            "account": self.account.to_dict(),
            "warnings": list(self.warnings),
        }


def display_ticker(raw: str) -> str:
    """AAPL_US_EQ -> AAPL. Leaves anything unexpected untouched."""
    if not raw:
        return ""
    head = raw.split("_", 1)[0]
    return head or raw


def parse_position(item: dict[str, Any], warnings: list[str]) -> Position:
    """Read one position, tolerating both the current and the older flat shape."""
    instrument = first_present(item, "instrument", default={}) or {}
    if not isinstance(instrument, dict):
        instrument = {}
    wallet = first_present(item, "walletImpact", default={}) or {}
    if not isinstance(wallet, dict):
        wallet = {}

    raw_ticker = str(first_present(instrument, "ticker") or first_present(item, "ticker") or "")
    if not raw_ticker:
        warnings.append("a position came back with no ticker and was skipped downstream")

    quantity = as_float(first_present(item, "quantity"))
    avg_price = as_float(first_present(item, "averagePricePaid", "averagePrice"))
    current_price = as_float(first_present(item, "currentPrice"))

    value = as_float(first_present(wallet, "currentValue"), default=quantity * current_price)
    cost = as_float(first_present(wallet, "totalCost"), default=quantity * avg_price)
    unrealized = as_float(
        first_present(wallet, "unrealizedProfitLoss") if wallet else None,
        # `ppl` is the old field name; fall back to value - cost if neither is present.
        default=as_float(first_present(item, "ppl"), default=value - cost),
    )

    return Position(
        ticker=display_ticker(raw_ticker),
        raw_ticker=raw_ticker,
        name=str(first_present(instrument, "name", default="") or ""),
        currency=str(
            first_present(wallet, "currency")
            or first_present(instrument, "currency", "currencyCode")
            or ""
        ),
        quantity=quantity,
        avg_price=avg_price,
        current_price=current_price,
        value=value,
        unrealized_pl=unrealized,
        isin=str(first_present(instrument, "isin", default="") or ""),
        opened_at=str(first_present(item, "createdAt", "initialFillDate", default="") or ""),
    )


def parse_positions(payload: Any, warnings: list[str]) -> list[Position]:
    if isinstance(payload, dict):  # a paginated wrapper would land here
        unwrapped = first_present(payload, "items", "data")
        if unwrapped is None:
            # Not a wrapper — an error object, or a shape we have never seen. Say so
            # loudly: silently returning "no positions" would read as an empty
            # portfolio, which is the one wrong answer that looks plausible.
            warnings.append(
                "positions payload was an object with no items/data list "
                f"(keys: {', '.join(sorted(payload)) or 'none'})"
            )
            return []
        payload = unwrapped
    if not isinstance(payload, list):
        warnings.append(f"positions payload was {type(payload).__name__}, expected a list")
        return []
    positions = [parse_position(item, warnings) for item in payload if isinstance(item, dict)]

    total = sum(p.value for p in positions)
    if total:
        for p in positions:
            p.pct_of_portfolio = round(p.value / total * 100, 2)
    return sorted(positions, key=lambda p: p.value, reverse=True)


def parse_account_summary(payload: Any, warnings: list[str]) -> AccountSummary:
    if not isinstance(payload, dict):
        warnings.append(f"account summary payload was {type(payload).__name__}, expected an object")
        return AccountSummary()
    cash = first_present(payload, "cash", default={}) or {}
    investments = first_present(payload, "investments", default={}) or {}
    if not isinstance(cash, dict):
        cash = {}
    if not isinstance(investments, dict):
        investments = {}
    return AccountSummary(
        currency=str(first_present(payload, "currency", "currencyCode", default="") or ""),
        total_value=as_float(first_present(payload, "totalValue")),
        invested=as_float(first_present(investments, "totalCost") or first_present(payload, "invested")),
        current_value=as_float(
            first_present(investments, "currentValue") or first_present(payload, "currentValue")
        ),
        unrealized_pl=as_float(
            first_present(investments, "unrealizedProfitLoss") or first_present(payload, "ppl")
        ),
        realized_pl=as_float(first_present(investments, "realizedProfitLoss")),
        cash_available=as_float(first_present(cash, "availableToTrade") or first_present(payload, "free")),
        cash_in_pies=as_float(first_present(cash, "inPies") or first_present(payload, "pieCash")),
        cash_reserved=as_float(first_present(cash, "reservedForOrders") or first_present(payload, "blocked")),
    )


class Trading212Client:
    def __init__(
        self,
        api_key: str,
        api_secret: str = "",
        env: str = "live",
        *,
        limiter: RateLimiter | None = None,
        recorder: Callable[[str, Any], None] | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = BASE_URLS.get(env, BASE_URLS["live"])
        self.env = env
        self._limiter = limiter or RateLimiter()
        self._recorder = recorder

    def _auth_header(self) -> str:
        if self.api_secret:
            token = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode()
            return f"Basic {token}"
        return self.api_key  # legacy single-key header

    def get(self, path: str) -> tuple[Any, dict[str, str]]:
        self._limiter.wait(path, MIN_INTERVAL.get(path, 1.0))
        try:
            resp = http_request(self.base_url + path, headers={"Authorization": self._auth_header()})
        except HttpError as exc:
            if exc.status == 403 and path in SCOPE_HINTS:
                raise HttpError(403, f"403 forbidden — {SCOPE_HINTS[path]}", exc.body) from exc
            if exc.status == 401:
                raise HttpError(401, "401 unauthorized — check T212_API_KEY / T212_API_SECRET", exc.body) from exc
            raise
        payload = resp.json()
        if self._recorder:
            self._recorder(path.strip("/").replace("/", "_"), payload)
        return payload, resp.rate_limit

    def fetch(self) -> SourceResult:
        """Positions + account summary as one result."""
        warnings: list[str] = []
        meta: dict[str, Any] = {"env": self.env}
        try:
            positions_payload, rl = self.get(POSITIONS_PATH)
            meta["positions_rate_limit"] = rl
        except HttpError as exc:
            return SourceResult.failure("trading212", str(exc), meta=meta)

        positions = parse_positions(positions_payload, warnings)

        # A summary failure is survivable: we still know the positions.
        account = AccountSummary()
        try:
            summary_payload, rl = self.get(SUMMARY_PATH)
            meta["summary_rate_limit"] = rl
            account = parse_account_summary(summary_payload, warnings)
        except HttpError as exc:
            warnings.append(f"account summary unavailable ({exc})")

        if not account.currency and positions:
            account.currency = positions[0].currency
        if not account.current_value:
            account.current_value = round(sum(p.value for p in positions), 2)

        data = PortfolioSnapshotData(positions=positions, account=account, warnings=warnings)
        return SourceResult.success("trading212", data, warnings=warnings, meta=meta)


def from_payloads(positions_payload: Any, summary_payload: Any) -> SourceResult:
    """Build a result from already-fetched payloads (fixtures, or a recorded run)."""
    warnings: list[str] = []
    positions = parse_positions(positions_payload, warnings)
    account = parse_account_summary(summary_payload, warnings)
    if not account.currency and positions:
        account.currency = positions[0].currency
    data = PortfolioSnapshotData(positions=positions, account=account, warnings=warnings)
    return SourceResult.success("trading212", data, warnings=warnings, meta={"env": "fixture"})
