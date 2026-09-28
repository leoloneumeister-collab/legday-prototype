"""Daily position snapshots and the diff between them.

This is the only thing in Jarvis that knows what "changed" means. Trading212 has no
"what moved since yesterday" endpoint, so each run writes today's positions to
state/snapshots/YYYY-MM-DD.json and diffs against the most recent earlier file.
Day one therefore has no diff, and says so rather than inventing one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = 1


def snapshot_dir(state_dir: Path) -> Path:
    return state_dir / "snapshots"


def build_snapshot(portfolio: Any, taken_on: str) -> dict[str, Any]:
    """portfolio is a PortfolioSnapshotData; kept duck-typed to avoid a cycle."""
    return {
        "version": SNAPSHOT_VERSION,
        "date": taken_on,
        **portfolio.to_dict(),
    }


def save_snapshot(state_dir: Path, snapshot: dict[str, Any]) -> Path:
    directory = snapshot_dir(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{snapshot['date']}.json"
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_previous(state_dir: Path, before: str) -> dict[str, Any] | None:
    """The newest snapshot strictly older than `before` (ISO date string)."""
    directory = snapshot_dir(state_dir)
    if not directory.is_dir():
        return None
    candidates = sorted(
        p for p in directory.glob("*.json") if p.stem < before
    )
    if not candidates:
        return None
    try:
        return json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


@dataclass
class PositionChange:
    ticker: str
    name: str
    kind: str                 # opened | closed | added | reduced | moved
    detail: str
    value_change: float = 0.0
    value_change_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "kind": self.kind,
            "detail": self.detail,
            "value_change": round(self.value_change, 2),
            "value_change_pct": round(self.value_change_pct, 2),
        }


@dataclass
class Diff:
    is_first_run: bool = False
    previous_date: str | None = None
    changes: list[PositionChange] = field(default_factory=list)
    total_value_change: float = 0.0
    total_value_change_pct: float = 0.0
    cash_change: float = 0.0
    quiet: bool = False        # nothing crossed the threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_first_run": self.is_first_run,
            "previous_date": self.previous_date,
            "changes": [c.to_dict() for c in self.changes],
            "total_value_change": round(self.total_value_change, 2),
            "total_value_change_pct": round(self.total_value_change_pct, 2),
            "cash_change": round(self.cash_change, 2),
            "quiet": self.quiet,
        }


def _index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for position in snapshot.get("positions", []) or []:
        ticker = position.get("ticker") or position.get("raw_ticker")
        if ticker:
            out[str(ticker)] = position
    return out


def _fmt(value: float) -> str:
    return f"{value:,.2f}"


def diff_snapshots(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    move_pct: float = 2.0,
    move_abs: float = 50.0,
) -> Diff:
    """Compare two snapshots.

    A position is reported when its quantity changed at all (that was a decision
    you made), or when its value moved by at least move_pct AND move_abs is also
    cleared — so a 5% wobble on a €30 position stays quiet.
    """
    if previous is None:
        return Diff(is_first_run=True)

    result = Diff(previous_date=previous.get("date"))
    now, before = _index(current), _index(previous)

    for ticker in sorted(set(now) | set(before)):
        new = now.get(ticker)
        old = before.get(ticker)
        if new and not old:
            result.changes.append(
                PositionChange(
                    ticker=ticker,
                    name=new.get("name", ""),
                    kind="opened",
                    detail=f"new position: {new.get('quantity', 0):g} @ {_fmt(float(new.get('avg_price') or 0))}",
                    value_change=float(new.get("value") or 0),
                    value_change_pct=100.0,
                )
            )
            continue
        if old and not new:
            result.changes.append(
                PositionChange(
                    ticker=ticker,
                    name=old.get("name", ""),
                    kind="closed",
                    detail=f"position closed (was worth {_fmt(float(old.get('value') or 0))})",
                    value_change=-float(old.get("value") or 0),
                    value_change_pct=-100.0,
                )
            )
            continue
        if not new or not old:  # pragma: no cover - covered by the branches above
            continue

        old_qty = float(old.get("quantity") or 0)
        new_qty = float(new.get("quantity") or 0)
        old_value = float(old.get("value") or 0)
        new_value = float(new.get("value") or 0)
        value_change = new_value - old_value
        value_pct = (value_change / old_value * 100) if old_value else 0.0

        if abs(new_qty - old_qty) > 1e-9:
            kind = "added" if new_qty > old_qty else "reduced"
            result.changes.append(
                PositionChange(
                    ticker=ticker,
                    name=new.get("name", ""),
                    kind=kind,
                    detail=f"quantity {old_qty:g} -> {new_qty:g}",
                    value_change=value_change,
                    value_change_pct=value_pct,
                )
            )
            continue

        if abs(value_pct) >= move_pct and abs(value_change) >= move_abs:
            direction = "up" if value_change > 0 else "down"
            result.changes.append(
                PositionChange(
                    ticker=ticker,
                    name=new.get("name", ""),
                    kind="moved",
                    detail=(
                        f"{direction} {abs(value_pct):.1f}% "
                        f"({_fmt(old_value)} -> {_fmt(new_value)})"
                    ),
                    value_change=value_change,
                    value_change_pct=value_pct,
                )
            )

    current_account = current.get("account") or {}
    previous_account = previous.get("account") or {}
    current_total = float(current_account.get("current_value") or 0)
    previous_total = float(previous_account.get("current_value") or 0)
    result.total_value_change = current_total - previous_total
    if previous_total:
        result.total_value_change_pct = result.total_value_change / previous_total * 100
    result.cash_change = float(current_account.get("cash_available") or 0) - float(
        previous_account.get("cash_available") or 0
    )

    # Biggest absolute moves first — that is the reading order.
    result.changes.sort(key=lambda c: abs(c.value_change), reverse=True)
    result.quiet = not result.changes
    return result


def today_iso() -> str:
    return date.today().isoformat()
