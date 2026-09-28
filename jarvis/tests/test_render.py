import unittest

from jarvis.brief import build_bundle, render_markdown
from jarvis.delivery import email as email_delivery
from jarvis.snapshots import diff_snapshots
from jarvis.sources import congress, finlight, trading212
from jarvis.sources.base import SourceResult

QUIET_BRIEF = {
    "bottom_line": "Nothing needs you today.",
    "changed": [],
    "matters": [],
    "needs_attention": [],
    "noise_filtered": 6,
}

BUSY_BRIEF = {
    "bottom_line": "One thing to look at: the export rule touches NVDA directly.",
    "changed": ["NVDA up 10.9% (1,983 -> 2,200)"],
    "matters": [
        {"claim": "Export restrictions widened.", "why": "Cuts a market NVDA sells into.", "tickers": ["NVDA"]}
    ],
    "needs_attention": [
        {"what": "NVDA is now 45% of the book", "suggested_action": "Decide whether to trim before earnings"}
    ],
    "noise_filtered": 3,
}


class TestRenderMarkdown(unittest.TestCase):
    def test_quiet_day_says_nothing_needed(self):
        md = render_markdown(QUIET_BRIEF, date="2026-09-28")
        self.assertIn("# Jarvis — 2026-09-28", md)
        self.assertIn("Nothing needs you today.", md)
        self.assertIn("Nothing. No action needed today.", md)
        self.assertNotIn("## What changed", md)
        self.assertNotIn("## What matters", md)
        self.assertIn("6 news items judged not worth mentioning", md)

    def test_busy_day_renders_every_section(self):
        md = render_markdown(BUSY_BRIEF, date="2026-09-28")
        self.assertIn("## What changed", md)
        self.assertIn("## What matters", md)
        self.assertIn("**Export restrictions widened.** _(NVDA)_", md)
        self.assertIn("Decide whether to trim before earnings", md)

    def test_footer_notes_are_surfaced(self):
        md = render_markdown(QUIET_BRIEF, date="2026-09-28", footer_notes=["news source failed: HTTP 500"])
        self.assertIn("news source failed: HTTP 500", md)

    def test_missing_bottom_line_does_not_crash(self):
        md = render_markdown({}, date="2026-09-28")
        self.assertIn("no bottom line returned", md)


class TestEmail(unittest.TestCase):
    def test_subject_front_loads_the_answer(self):
        self.assertEqual(
            email_delivery.subject_for("2026-09-28", QUIET_BRIEF),
            "Jarvis 2026-09-28 — nothing needs you",
        )
        self.assertIn("NVDA is now 45% of the book", email_delivery.subject_for("2026-09-28", BUSY_BRIEF))

    def test_subject_for_matters_without_attention(self):
        brief = dict(BUSY_BRIEF, needs_attention=[])
        self.assertEqual(
            email_delivery.subject_for("2026-09-28", brief),
            "Jarvis 2026-09-28 — 1 worth knowing, nothing to do",
        )

    def test_html_conversion_escapes_and_bolds(self):
        html = email_delivery.markdown_to_html(render_markdown(BUSY_BRIEF, date="2026-09-28"))
        self.assertIn("<h2>Jarvis — 2026-09-28</h2>", html)
        self.assertIn("<strong>Export restrictions widened.</strong>", html)
        self.assertIn("<ul>", html)
        self.assertEqual(html.count("<ul>"), html.count("</ul>"))

    def test_html_escapes_injected_markup(self):
        brief = dict(QUIET_BRIEF, bottom_line="<script>alert(1)</script> & co")
        html = email_delivery.markdown_to_html(render_markdown(brief, date="2026-09-28"))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&amp; co", html)

    def test_send_uses_starttls_and_login(self):
        calls = []

        class FakeSMTP:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def ehlo(self): calls.append("ehlo")
            def has_extn(self, name): return name == "starttls"
            def starttls(self): calls.append("starttls")
            def login(self, u, p): calls.append(("login", u))
            def send_message(self, msg): calls.append(("send", msg["Subject"], msg["To"]))

        email_delivery.send(
            host="smtp.example.com", port=587, user="me@example.com", password="pw",
            sender="me@example.com", to="me@example.com", subject="S", markdown="# hi\n",
            smtp_factory=FakeSMTP,
        )
        self.assertIn("starttls", calls)
        self.assertIn(("login", "me@example.com"), calls)
        self.assertIn(("send", "S", "me@example.com"), calls)


class TestBundle(unittest.TestCase):
    def _portfolio(self):
        return trading212.from_payloads(
            [{
                "instrument": {"ticker": "NVDA_US_EQ", "name": "NVIDIA Corporation", "currency": "USD"},
                "quantity": 10, "averagePricePaid": 100.0, "currentPrice": 150.0,
                "walletImpact": {"currency": "EUR", "currentValue": 1500.0, "totalCost": 1000.0, "unrealizedProfitLoss": 500.0},
            }],
            {"currency": "EUR", "totalValue": 1600.0,
             "cash": {"availableToTrade": 100.0, "inPies": 0, "reservedForOrders": 0},
             "investments": {"currentValue": 1500.0, "totalCost": 1000.0, "unrealizedProfitLoss": 500.0, "realizedProfitLoss": 0}},
        )

    def test_first_run_tells_the_model_not_to_claim_changes(self):
        bundle = build_bundle(
            today="2026-09-28",
            portfolio=self._portfolio(),
            news=finlight.from_payload({"articles": []}, tickers=["NVDA"]),
            congress=congress.fetch(""),
            diff=diff_snapshots({"positions": [], "account": {}}, None),
        )
        self.assertIn("first run", bundle.text)
        self.assertIn("Do not describe anything as new or moved", bundle.text)

    def test_failed_source_is_stated_not_hidden(self):
        bundle = build_bundle(
            today="2026-09-28",
            portfolio=SourceResult.failure("trading212", "401 unauthorized"),
            news=SourceResult.failure("finlight", "HTTP 500"),
            congress=congress.fetch(""),
            diff=diff_snapshots({"positions": [], "account": {}}, None),
        )
        self.assertIn("UNAVAILABLE — 401 unauthorized", bundle.text)
        self.assertIn("UNAVAILABLE — HTTP 500", bundle.text)
        self.assertEqual(len(bundle.source_notes), 2)

    def test_positions_and_percentages_reach_the_prompt(self):
        bundle = build_bundle(
            today="2026-09-28",
            portfolio=self._portfolio(),
            news=finlight.from_payload({"articles": []}, tickers=["NVDA"]),
            congress=congress.fetch(""),
            diff=diff_snapshots({"positions": [], "account": {}}, None),
        )
        self.assertIn("NVDA (NVIDIA Corporation)", bundle.text)
        self.assertIn("100.0% of portfolio", bundle.text)
        self.assertIn("unrealized P/L 500.00 (+50.0%)", bundle.text)

    def test_congress_absence_is_explicit(self):
        bundle = build_bundle(
            today="2026-09-28",
            portfolio=self._portfolio(),
            news=finlight.from_payload({"articles": []}),
            congress=congress.fetch(""),
            diff=diff_snapshots({"positions": [], "account": {}}, None),
        )
        self.assertIn("Do not speculate about congressional or insider activity", bundle.text)


if __name__ == "__main__":
    unittest.main()
