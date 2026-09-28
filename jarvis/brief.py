"""Turn sources + diff into the text the model sees, and the brief into markdown."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .sources.base import SourceResult


@dataclass
class Bundle:
    """Everything the model is given, plus the notes a human needs to trust it."""

    date: str
    text: str
    source_notes: list[str] = field(default_factory=list)
    news_count: int = 0

    def __str__(self) -> str:  # so --dry-run can just print it
        return self.text


def _money(value: float, currency: str) -> str:
    return f"{value:,.2f} {currency}".strip()


def build_bundle(
    *,
    today: str,
    portfolio: SourceResult,
    news: SourceResult,
    congress: SourceResult,
    diff: Any,
) -> Bundle:
    lines: list[str] = [f"DATE: {today}", ""]
    notes: list[str] = []

    # --- positions ---------------------------------------------------------
    lines.append("## PORTFOLIO")
    if portfolio.ok and portfolio.data and portfolio.data.positions:
        account = portfolio.data.account
        currency = account.currency or ""
        lines.append(
            f"Total invested value: {_money(account.current_value, currency)}"
            f" | cost basis: {_money(account.invested, currency)}"
            f" | unrealized P/L: {_money(account.unrealized_pl, currency)}"
        )
        lines.append(
            f"Cash available: {_money(account.cash_available, currency)}"
            f" | reserved for orders: {_money(account.cash_reserved, currency)}"
        )
        lines.append("")
        lines.append("Positions (largest first):")
        for p in portfolio.data.positions:
            pl_pct = (p.unrealized_pl / (p.value - p.unrealized_pl) * 100) if (p.value - p.unrealized_pl) else 0.0
            lines.append(
                f"- {p.ticker} ({p.name or 'name unknown'}): {p.quantity:g} shares, "
                f"value {p.value:,.2f} {p.currency}, {p.pct_of_portfolio:.1f}% of portfolio, "
                f"unrealized P/L {p.unrealized_pl:,.2f} ({pl_pct:+.1f}%), "
                f"avg cost {p.avg_price:,.2f} vs current {p.current_price:,.2f}"
            )
        for warning in portfolio.data.warnings:
            notes.append(f"portfolio: {warning}")
    else:
        lines.append(f"UNAVAILABLE — {portfolio.error or 'no positions returned'}.")
        notes.append(f"portfolio source failed: {portfolio.error}")
    lines.append("")

    # --- what changed ------------------------------------------------------
    lines.append("## WHAT CHANGED SINCE THE LAST BRIEF")
    if getattr(diff, "is_first_run", False):
        lines.append(
            "This is the first run — there is no earlier snapshot to compare against, "
            "so nothing here is a change. Do not describe anything as new or moved."
        )
    elif getattr(diff, "quiet", False):
        lines.append(
            f"Nothing crossed the reporting threshold since {diff.previous_date}. "
            "Treat this as a flat day."
        )
    else:
        lines.append(f"Compared against the snapshot from {diff.previous_date}:")
        lines.append(
            f"- total invested value change: {diff.total_value_change:+,.2f} "
            f"({diff.total_value_change_pct:+.2f}%)"
        )
        if abs(diff.cash_change) > 0.005:
            lines.append(f"- cash available change: {diff.cash_change:+,.2f}")
        for change in diff.changes:
            lines.append(
                f"- {change.ticker} [{change.kind}]: {change.detail} "
                f"(value {change.value_change:+,.2f})"
            )
    lines.append("")

    # --- news --------------------------------------------------------------
    lines.append("## NEWS (already filtered to holdings and thesis keywords)")
    news_count = 0
    if news.ok and news.data:
        news_count = len(news.data)
        filtered_out = news.meta.get("filtered_out", 0)
        lines.append(
            f"{news_count} items kept out of {news.meta.get('fetched', news_count)} fetched; "
            f"{filtered_out} were dropped as unrelated before you saw them."
        )
        lines.append("")
        for index, article in enumerate(news.data, start=1):
            matched = ", ".join(article.matched) or "none"
            summary = article.summary[:400]
            lines.append(
                f"[{index}] {article.title}\n"
                f"    source: {article.source or 'unknown'} | published: {article.published_at or 'unknown'}\n"
                f"    matched: {matched}\n"
                f"    {summary}"
            )
    else:
        lines.append(f"UNAVAILABLE — {news.error or 'no articles'}. Say so rather than guessing at the news.")
        notes.append(f"news source failed: {news.error}")
    lines.append("")

    # --- congress / insider ------------------------------------------------
    lines.append("## CONGRESSIONAL / INSIDER TRADES")
    if congress.ok and congress.data:
        for trade in congress.data:
            lines.append(
                f"- {trade.person} {trade.action} {trade.ticker} {trade.amount} "
                f"(transacted {trade.transaction_date}, disclosed {trade.disclosed_date})"
            )
    else:
        lines.append(
            f"NOT AVAILABLE — {congress.error or 'no provider'}. "
            "Do not speculate about congressional or insider activity."
        )
    lines.append("")

    lines.append(
        "## YOUR TASK\n"
        "Write today's brief as JSON matching the required schema. Apply the bar in the "
        "profile: if nothing clears it, return an empty `matters`/`needs_attention` and say "
        "so in `bottom_line`."
    )

    return Bundle(date=today, text="\n".join(lines), source_notes=notes, news_count=news_count)


def render_markdown(brief: dict[str, Any], *, date: str, footer_notes: list[str] | None = None) -> str:
    out: list[str] = [f"# Jarvis — {date}", ""]
    out.append(brief.get("bottom_line", "").strip() or "_(no bottom line returned)_")
    out.append("")

    changed = brief.get("changed") or []
    if changed:
        out.append("## What changed")
        out.extend(f"- {item}" for item in changed)
        out.append("")

    matters = brief.get("matters") or []
    if matters:
        out.append("## What matters")
        for item in matters:
            tickers = ", ".join(item.get("tickers") or [])
            head = f"**{item.get('claim', '').strip()}**"
            if tickers:
                head += f" _({tickers})_"
            out.append(f"- {head}  \n  {item.get('why', '').strip()}")
        out.append("")

    attention = brief.get("needs_attention") or []
    out.append("## Needs your attention")
    if attention:
        for item in attention:
            out.append(f"- **{item.get('what', '').strip()}** → {item.get('suggested_action', '').strip()}")
    else:
        out.append("- Nothing. No action needed today.")
    out.append("")

    noise = brief.get("noise_filtered")
    if isinstance(noise, int) and noise > 0:
        out.append(f"_{noise} news items judged not worth mentioning._")
        out.append("")

    for note in footer_notes or []:
        out.append(f"> ⚠️ {note}")

    return "\n".join(out).rstrip() + "\n"
