import json
import tempfile
import unittest
from pathlib import Path

from jarvis.snapshots import diff_snapshots, load_previous, save_snapshot


def snap(date, positions, account=None):
    return {
        "version": 1,
        "date": date,
        "positions": positions,
        "account": account or {"currency": "EUR", "current_value": sum(p["value"] for p in positions), "cash_available": 100.0},
        "warnings": [],
    }


def pos(ticker, quantity, value, name="", avg_price=10.0):
    return {"ticker": ticker, "name": name or ticker, "quantity": quantity, "value": value, "avg_price": avg_price}


class TestDiff(unittest.TestCase):
    def test_first_run_has_no_changes(self):
        diff = diff_snapshots(snap("2026-09-28", [pos("NVDA", 10, 1500)]), None)
        self.assertTrue(diff.is_first_run)
        self.assertEqual(diff.changes, [])
        self.assertIsNone(diff.previous_date)

    def test_opened_position(self):
        before = snap("2026-09-27", [pos("NVDA", 10, 1500)])
        after = snap("2026-09-28", [pos("NVDA", 10, 1500), pos("ASML", 1, 700)])
        diff = diff_snapshots(after, before)
        kinds = {c.ticker: c.kind for c in diff.changes}
        self.assertEqual(kinds["ASML"], "opened")
        self.assertNotIn("NVDA", kinds)

    def test_closed_position(self):
        before = snap("2026-09-27", [pos("NVDA", 10, 1500), pos("ASML", 1, 700)])
        after = snap("2026-09-28", [pos("NVDA", 10, 1500)])
        diff = diff_snapshots(after, before)
        change = next(c for c in diff.changes if c.ticker == "ASML")
        self.assertEqual(change.kind, "closed")
        self.assertEqual(change.value_change, -700)

    def test_quantity_change_is_always_reported_even_if_tiny(self):
        # A quantity change is a decision the user made; it is never "below threshold".
        before = snap("2026-09-27", [pos("VUAA", 4.0, 400)])
        after = snap("2026-09-28", [pos("VUAA", 4.2, 420)])
        diff = diff_snapshots(after, before, move_pct=99.0, move_abs=10_000.0)
        change = next(c for c in diff.changes if c.ticker == "VUAA")
        self.assertEqual(change.kind, "added")
        self.assertIn("4 -> 4.2", change.detail)

    def test_reduced_quantity(self):
        diff = diff_snapshots(
            snap("2026-09-28", [pos("VUAA", 2.0, 200)]),
            snap("2026-09-27", [pos("VUAA", 4.0, 400)]),
        )
        self.assertEqual(diff.changes[0].kind, "reduced")

    def test_small_percentage_move_on_small_position_stays_quiet(self):
        before = snap("2026-09-27", [pos("VUAA", 4.2, 455)])
        after = snap("2026-09-28", [pos("VUAA", 4.2, 470)])   # +3.3% but only +15
        diff = diff_snapshots(after, before, move_pct=2.0, move_abs=50.0)
        self.assertTrue(diff.quiet)
        self.assertEqual(diff.changes, [])

    def test_move_reported_when_both_thresholds_cleared(self):
        before = snap("2026-09-27", [pos("NVDA", 12.4, 1983)])
        after = snap("2026-09-28", [pos("NVDA", 12.4, 2200)])  # +10.9% and +217
        diff = diff_snapshots(after, before, move_pct=2.0, move_abs=50.0)
        self.assertFalse(diff.quiet)
        change = diff.changes[0]
        self.assertEqual(change.kind, "moved")
        self.assertIn("up 10.9%", change.detail)

    def test_large_absolute_but_small_percent_stays_quiet(self):
        before = snap("2026-09-27", [pos("BIG", 1000, 100_000)])
        after = snap("2026-09-28", [pos("BIG", 1000, 100_600)])  # +600 but only +0.6%
        diff = diff_snapshots(after, before, move_pct=2.0, move_abs=50.0)
        self.assertTrue(diff.quiet)

    def test_changes_sorted_by_absolute_value_impact(self):
        before = snap("2026-09-27", [pos("A", 1, 1000), pos("B", 1, 1000)])
        after = snap("2026-09-28", [pos("A", 1, 1100), pos("B", 1, 1500)])
        diff = diff_snapshots(after, before)
        self.assertEqual([c.ticker for c in diff.changes], ["B", "A"])

    def test_totals_and_cash(self):
        before = snap("2026-09-27", [pos("NVDA", 10, 1000)], {"currency": "EUR", "current_value": 1000.0, "cash_available": 100.0})
        after = snap("2026-09-28", [pos("NVDA", 10, 1100)], {"currency": "EUR", "current_value": 1100.0, "cash_available": 80.0})
        diff = diff_snapshots(after, before)
        self.assertAlmostEqual(diff.total_value_change, 100.0)
        self.assertAlmostEqual(diff.total_value_change_pct, 10.0)
        self.assertAlmostEqual(diff.cash_change, -20.0)


class TestSnapshotStorage(unittest.TestCase):
    def test_save_and_load_previous_picks_newest_older_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            for date in ("2026-09-20", "2026-09-25", "2026-09-28"):
                save_snapshot(state, snap(date, [pos("NVDA", 10, 1500)]))
            previous = load_previous(state, "2026-09-28")
            self.assertEqual(previous["date"], "2026-09-25")

    def test_no_previous_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_previous(Path(tmp), "2026-09-28"))

    def test_corrupt_snapshot_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            save_snapshot(state, snap("2026-09-27", [pos("NVDA", 10, 1500)]))
            (state / "snapshots" / "2026-09-27.json").write_text("{not json", encoding="utf-8")
            self.assertIsNone(load_previous(state, "2026-09-28"))

    def test_roundtrip_is_json_serializable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = save_snapshot(Path(tmp), snap("2026-09-28", [pos("NVDA", 10, 1500)]))
            self.assertEqual(json.loads(path.read_text())["date"], "2026-09-28")


if __name__ == "__main__":
    unittest.main()
