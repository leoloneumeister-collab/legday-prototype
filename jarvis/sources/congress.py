"""Congressional / insider ("whale") trades — adapter seam, no live provider yet.

Deliberately unwired. The shape below is what the brief consumes, so adding a
provider is one function, not a refactor:

    fetch(provider, ...) -> SourceResult(data=[Trade, ...])

Candidate providers, in the order worth trying:

1. Quiver Quant — GET https://api.quiverquant.com/beta/live/congresstrading
   with `Authorization: Bearer <token>`. Paid, but the cleanest data.
2. disclosedcapitol.com — free tier, JSON, STOCK Act filings, webhooks.
3. congressinvests.com — 100 requests/day free, no key at all.
4. The official portals (disclosures-clerk.house.gov, efdsearch.senate.gov) —
   free and authoritative, but PDF scraping. Not MVP work.

Why it is a stub rather than a guess: every one of those hosts is unreachable from
the environment this was built in, so a parser written against them could not be
run even once. Pick a provider, run `jarvis doctor --record`, and the recorded
payload turns this into ~20 lines.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .base import SourceResult, as_float, first_present

SUPPORTED_PROVIDERS = ("quiver", "disclosedcapitol", "congressinvests")


@dataclass
class Trade:
    """One disclosed transaction, normalized."""

    person: str
    ticker: str
    action: str          # buy | sell | exchange | unknown
    amount: str          # disclosures give ranges ("$15,001 - $50,000"), so keep text
    transaction_date: str
    disclosed_date: str
    chamber: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_trade(raw: dict[str, Any], source: str = "") -> Trade:
    """Best-effort normalization, written to survive whichever provider is chosen."""
    action = str(first_present(raw, "transaction", "type", "action", "transaction_type", default="") or "")
    amount = first_present(raw, "amount", "range", "value", "amount_range", default="")
    return Trade(
        person=str(first_present(raw, "representative", "senator", "member", "name", default="") or ""),
        ticker=str(first_present(raw, "ticker", "symbol", default="") or "").upper(),
        action=_normalize_action(action),
        amount=amount if isinstance(amount, str) else f"{as_float(amount):,.0f}",
        transaction_date=str(
            first_present(raw, "transactionDate", "transaction_date", "date", default="") or ""
        ),
        disclosed_date=str(
            first_present(raw, "disclosureDate", "disclosure_date", "filed", "reportDate", default="") or ""
        ),
        chamber=str(first_present(raw, "chamber", "house", default="") or ""),
        source=source,
    )


def _normalize_action(value: str) -> str:
    low = value.lower()
    if "purchase" in low or low.startswith("buy") or low == "p":
        return "buy"
    if "sale" in low or "sell" in low or low in ("s", "s (partial)"):
        return "sell"
    if "exchange" in low:
        return "exchange"
    return low or "unknown"


def fetch(provider: str = "", **_: Any) -> SourceResult:
    """No provider is wired yet — this reports that, it does not fail the brief."""
    if not provider:
        return SourceResult.failure(
            "congress",
            "not configured (set JARVIS_CONGRESS_PROVIDER once a provider is wired up)",
        )
    return SourceResult.failure(
        "congress",
        f"provider {provider!r} is not implemented yet; see jarvis/sources/congress.py",
    )


def from_payload(payload: Any, source: str = "fixture") -> SourceResult:
    """Used by the offline path and by whichever provider lands first."""
    items: list[dict[str, Any]] = []
    if isinstance(payload, list):
        items = [i for i in payload if isinstance(i, dict)]
    elif isinstance(payload, dict):
        for key in ("data", "items", "trades", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                items = [i for i in value if isinstance(i, dict)]
                break
    trades = [parse_trade(item, source) for item in items]
    return SourceResult.success("congress", trades, meta={"count": len(trades), "source": source})
