import unittest

from jarvis.sources import trading212 as t


CURRENT_SHAPE = [
    {
        "instrument": {"ticker": "NVDA_US_EQ", "name": "NVIDIA Corporation", "isin": "US67066G1040", "currency": "USD"},
        "quantity": 10,
        "averagePricePaid": 100.0,
        "currentPrice": 150.0,
        "createdAt": "2026-02-11T09:31:02Z",
        "walletImpact": {"currency": "EUR", "currentValue": 1500.0, "totalCost": 1000.0, "unrealizedProfitLoss": 500.0, "fxImpact": -3.0},
    },
    {
        "instrument": {"ticker": "VUAA_EQ", "name": "Vanguard S&P 500 UCITS ETF", "currency": "EUR"},
        "quantity": 5,
        "averagePricePaid": 100.0,
        "currentPrice": 100.0,
        "walletImpact": {"currency": "EUR", "currentValue": 500.0, "totalCost": 500.0, "unrealizedProfitLoss": 0.0},
    },
]

# The shape most tutorials (and my own first instinct) assume: flat ticker, `ppl`,
# no instrument object, no walletImpact. Jarvis must still produce something usable.
LEGACY_SHAPE = [
    {
        "ticker": "NVDA_US_EQ",
        "quantity": 10,
        "averagePrice": 100.0,
        "currentPrice": 150.0,
        "ppl": 500.0,
        "initialFillDate": "2026-02-11T09:31:02Z",
    }
]


class TestPositionParsing(unittest.TestCase):
    def test_current_shape(self):
        warnings = []
        positions = t.parse_positions(CURRENT_SHAPE, warnings)
        self.assertEqual(warnings, [])
        self.assertEqual([p.ticker for p in positions], ["NVDA", "VUAA"])
        nvda = positions[0]
        self.assertEqual(nvda.name, "NVIDIA Corporation")
        self.assertEqual(nvda.value, 1500.0)
        self.assertEqual(nvda.unrealized_pl, 500.0)
        self.assertEqual(nvda.currency, "EUR")

    def test_sorted_by_value_with_percentages(self):
        positions = t.parse_positions(CURRENT_SHAPE, [])
        self.assertGreater(positions[0].value, positions[1].value)
        self.assertEqual(positions[0].pct_of_portfolio, 75.0)
        self.assertEqual(positions[1].pct_of_portfolio, 25.0)
        self.assertAlmostEqual(sum(p.pct_of_portfolio for p in positions), 100.0, places=2)

    def test_legacy_shape_still_parses(self):
        positions = t.parse_positions(LEGACY_SHAPE, [])
        self.assertEqual(len(positions), 1)
        p = positions[0]
        self.assertEqual(p.ticker, "NVDA")
        self.assertEqual(p.avg_price, 100.0)
        self.assertEqual(p.value, 1500.0)   # derived from quantity * currentPrice
        self.assertEqual(p.unrealized_pl, 500.0)  # from `ppl`
        self.assertEqual(p.opened_at, "2026-02-11T09:31:02Z")

    def test_missing_fields_do_not_raise(self):
        warnings = []
        positions = t.parse_positions([{"instrument": {}}], warnings)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].quantity, 0.0)
        self.assertTrue(warnings)

    def test_unexpected_payload_type_is_reported(self):
        warnings = []
        self.assertEqual(t.parse_positions({"error": "nope"}, warnings), [])
        self.assertTrue(warnings)

    def test_display_ticker(self):
        self.assertEqual(t.display_ticker("AAPL_US_EQ"), "AAPL")
        self.assertEqual(t.display_ticker("ASML_EQ"), "ASML")
        self.assertEqual(t.display_ticker("WEIRD"), "WEIRD")
        self.assertEqual(t.display_ticker(""), "")


class TestAccountSummary(unittest.TestCase):
    def test_current_shape(self):
        payload = {
            "id": 1,
            "currency": "EUR",
            "totalValue": 4712.27,
            "cash": {"availableToTrade": 360.0, "inPies": 0.0, "reservedForOrders": 12.0},
            "investments": {"currentValue": 4352.27, "totalCost": 3623.96, "unrealizedProfitLoss": 728.31, "realizedProfitLoss": 142.08},
        }
        account = t.parse_account_summary(payload, [])
        self.assertEqual(account.currency, "EUR")
        self.assertEqual(account.cash_available, 360.0)
        self.assertEqual(account.cash_reserved, 12.0)
        self.assertEqual(account.invested, 3623.96)
        self.assertEqual(account.realized_pl, 142.08)

    def test_legacy_cash_shape(self):
        account = t.parse_account_summary({"free": 100.0, "invested": 900.0, "ppl": 20.0}, [])
        self.assertEqual(account.cash_available, 100.0)
        self.assertEqual(account.invested, 900.0)
        self.assertEqual(account.unrealized_pl, 20.0)


class TestAuthHeader(unittest.TestCase):
    def test_basic_auth_when_secret_present(self):
        client = t.Trading212Client("key", "secret")
        self.assertEqual(client._auth_header(), "Basic a2V5OnNlY3JldA==")

    def test_legacy_header_without_secret(self):
        client = t.Trading212Client("rawkey", "")
        self.assertEqual(client._auth_header(), "rawkey")

    def test_env_selects_base_url(self):
        self.assertIn("demo.trading212.com", t.Trading212Client("k", "s", "demo").base_url)
        self.assertIn("live.trading212.com", t.Trading212Client("k", "s", "live").base_url)
        self.assertIn("live.trading212.com", t.Trading212Client("k", "s", "nonsense").base_url)


if __name__ == "__main__":
    unittest.main()
