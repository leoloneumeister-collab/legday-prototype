import unittest

from jarvis.sources import finlight


RAW = [
    {"title": "NVDA earnings set for November", "summary": "NVIDIA confirmed its date.", "source": "CNBC", "link": "u1", "publishDate": "2026-09-28T05:00:00Z"},
    {"title": "NVDA earnings set for November", "summary": "duplicate headline", "source": "Other", "link": "u2", "publishDate": "2026-09-28T04:00:00Z"},
    {"title": "Local bakery expands to three towns", "summary": "No market exposure.", "source": "Regional", "link": "u3", "publishDate": "2026-09-27T12:00:00Z"},
    {"title": "US widens AI chip export restrictions", "summary": "New license requirements for accelerators.", "source": "Reuters", "link": "u4", "publishDate": "2026-09-28T06:00:00Z"},
    {"headline": "ASML books record orders", "description": "High-NA EUV commitments.", "publisher": "Bloomberg", "url": "u5", "publishedAt": "2026-09-28T04:30:00Z"},
]


class TestArticleParsing(unittest.TestCase):
    def test_alternate_field_names(self):
        article = finlight.parse_article(RAW[4])
        self.assertEqual(article.title, "ASML books record orders")
        self.assertEqual(article.summary, "High-NA EUV commitments.")
        self.assertEqual(article.source, "Bloomberg")
        self.assertEqual(article.url, "u5")
        self.assertEqual(article.published_at, "2026-09-28T04:30:00Z")

    def test_extract_from_several_container_keys(self):
        for key in ("articles", "data", "items", "results"):
            self.assertEqual(len(finlight._extract_articles({key: RAW})), 5)
        self.assertEqual(len(finlight._extract_articles(RAW)), 5)
        self.assertEqual(finlight._extract_articles({"unexpected": 1}), [])


class TestSelection(unittest.TestCase):
    def test_dedupes_by_title_and_filters_irrelevant(self):
        kept, dropped = finlight.select(RAW, tickers=["NVDA", "ASML"], names=["NVIDIA Corporation"])
        titles = [a.title for a in kept]
        self.assertEqual(titles.count("NVDA earnings set for November"), 1)
        self.assertNotIn("Local bakery expands to three towns", titles)
        self.assertEqual(dropped, 1)

    def test_thesis_keyword_match_without_a_holding(self):
        kept, _ = finlight.select(RAW, tickers=["MSFT"], names=[])
        matched = {a.title: a.matched for a in kept}
        chip = "US widens AI chip export restrictions"
        self.assertIn(chip, matched)
        self.assertTrue(all(m.startswith("thesis:") for m in matched[chip]))

    def test_holding_hits_rank_above_thesis_only(self):
        kept, _ = finlight.select(RAW, tickers=["NVDA"], names=[])
        # First item must be one that names a holding, not a generic thesis match.
        self.assertTrue(any(not m.startswith("thesis:") for m in kept[0].matched))

    def test_ticker_matching_is_word_bounded(self):
        raw = [{"title": "ANVDAX corp announces nothing", "summary": "", "publishDate": ""}]
        kept, dropped = finlight.select(raw, tickers=["NVDA"], names=[])
        self.assertEqual(kept, [])
        self.assertEqual(dropped, 1)

    def test_name_matching_uses_first_significant_word(self):
        raw = [{"title": "Nvidia supply chain update", "summary": "", "publishDate": ""}]
        kept, _ = finlight.select(raw, tickers=[], names=["NVIDIA Corporation"])
        self.assertEqual(len(kept), 1)
        self.assertIn("nvidia", kept[0].matched)

    def test_limit_is_respected(self):
        kept, _ = finlight.select(RAW, tickers=["NVDA", "ASML"], names=[], limit=1)
        self.assertEqual(len(kept), 1)

    def test_untitled_items_are_skipped(self):
        kept, _ = finlight.select([{"summary": "no title"}], tickers=["NVDA"], names=[])
        self.assertEqual(kept, [])

    def test_from_payload_reports_counts(self):
        result = finlight.from_payload({"articles": RAW}, tickers=["NVDA"], names=[])
        self.assertTrue(result.ok)
        self.assertEqual(result.meta["fetched"], 5)
        self.assertEqual(result.meta["kept"], len(result.data))


if __name__ == "__main__":
    unittest.main()
