"""News via Finlight — the feed the AIFA app already uses.

Reused from aifa-news/src/app/api/news/route.ts:
    POST https://api.finlight.me/v2/articles   header: X-API-KEY

The response shape is not formally documented, so every field is read through
first_present() and the article list is looked for under several container keys.
Filtering to the portfolio happens here, before the model sees anything: the whole
feed would be tens of thousands of tokens of mostly-irrelevant headlines.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

from .base import HttpError, SourceResult, first_present, http_request

ARTICLES_URL = "https://api.finlight.me/v2/articles"

# Thesis keywords: news that matters to an AI/tech-momentum book even when it names
# no holding of yours. Kept here (not in profile.md) because it is matching
# machinery, not judgement — the model does the judging.
THESIS_KEYWORDS = (
    "artificial intelligence",
    "ai chip",
    "ai capex",
    "data center",
    "datacenter",
    "gpu",
    "semiconductor",
    "chip export",
    "export control",
    "cloud capex",
    "hyperscaler",
    "interest rate",
    "fed ",
    "federal reserve",
    "inflation",
    "tariff",
)

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass
class Article:
    title: str
    summary: str
    source: str
    url: str
    published_at: str
    matched: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_title(title: str) -> str:
    return " ".join(_WORD_RE.findall(title.lower()))


def _extract_articles(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [a for a in payload if isinstance(a, dict)]
    if isinstance(payload, dict):
        for key in ("articles", "data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [a for a in value if isinstance(a, dict)]
    return []


def parse_article(raw: dict[str, Any]) -> Article:
    return Article(
        title=str(first_present(raw, "title", "headline", default="") or "").strip(),
        summary=str(
            first_present(raw, "summary", "description", "content", "snippet", default="") or ""
        ).strip(),
        source=str(first_present(raw, "source", "publisher", "site", default="") or "").strip(),
        url=str(first_present(raw, "link", "url", default="") or "").strip(),
        published_at=str(
            first_present(raw, "publishDate", "publishedAt", "published_at", "date", "datetime", default="")
            or ""
        ).strip(),
        matched=[],
    )


def relevance(article: Article, tickers: Iterable[str], names: Iterable[str]) -> list[str]:
    """Which of the user's holdings / thesis keywords this article touches."""
    haystack = f"{article.title} {article.summary}".lower()
    hits: list[str] = []

    for ticker in tickers:
        if not ticker:
            continue
        if re.search(rf"\b{re.escape(ticker.lower())}\b", haystack):
            hits.append(ticker)

    for name in names:
        # First significant word of the instrument name ("NVIDIA Corp" -> "nvidia").
        head = next((w for w in _WORD_RE.findall(name.lower()) if len(w) > 3), "")
        if head and head in haystack and head not in hits:
            hits.append(head)

    for keyword in THESIS_KEYWORDS:
        if keyword in haystack:
            hits.append(f"thesis:{keyword.strip()}")

    # A ticker and its company name often both hit ("ASML", "asml"); the model does
    # not need to see that twice.
    deduped: list[str] = []
    for hit in hits:
        if hit.lower() not in {h.lower() for h in deduped}:
            deduped.append(hit)
    return deduped


def select(
    raw_articles: list[dict[str, Any]],
    *,
    tickers: Iterable[str] = (),
    names: Iterable[str] = (),
    limit: int = 40,
) -> tuple[list[Article], int]:
    """Dedupe, score, sort. Returns (kept, dropped_as_irrelevant)."""
    tickers = list(tickers)
    names = list(names)
    seen: set[str] = set()
    relevant: list[Article] = []
    dropped = 0

    for raw in raw_articles:
        article = parse_article(raw)
        if not article.title:
            continue
        key = _normalize_title(article.title)
        if key in seen:
            continue
        seen.add(key)

        article.matched = relevance(article, tickers, names)
        if not article.matched:
            dropped += 1
            continue
        relevant.append(article)

    # Direct holding hits first, then newest. Sorting a mixed bag of date formats
    # is hopeless, so string-sort the timestamps — ISO-8601 sorts correctly and
    # anything else at least sorts consistently.
    def rank(a: Article) -> tuple[int, str]:
        holding_hits = sum(1 for m in a.matched if not m.startswith("thesis:"))
        return (holding_hits, a.published_at)

    relevant.sort(key=rank, reverse=True)
    return relevant[:limit], dropped


def fetch(
    api_key: str,
    *,
    tickers: Iterable[str] = (),
    names: Iterable[str] = (),
    limit: int = 40,
    recorder: Callable[[str, Any], None] | None = None,
) -> SourceResult:
    try:
        resp = http_request(
            ARTICLES_URL,
            method="POST",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            body=json.dumps({}).encode("utf-8"),
        )
        payload = resp.json()
    except HttpError as exc:
        return SourceResult.failure("finlight", str(exc))

    if recorder:
        recorder("finlight_articles", payload)

    raw_articles = _extract_articles(payload)
    if not raw_articles:
        return SourceResult.failure("finlight", "no articles found in the response")

    kept, dropped = select(raw_articles, tickers=tickers, names=names, limit=limit)
    return SourceResult.success(
        "finlight",
        kept,
        meta={"fetched": len(raw_articles), "kept": len(kept), "filtered_out": dropped},
    )


def from_payload(
    payload: Any,
    *,
    tickers: Iterable[str] = (),
    names: Iterable[str] = (),
    limit: int = 40,
) -> SourceResult:
    raw_articles = _extract_articles(payload)
    kept, dropped = select(raw_articles, tickers=tickers, names=names, limit=limit)
    return SourceResult.success(
        "finlight",
        kept,
        meta={"fetched": len(raw_articles), "kept": len(kept), "filtered_out": dropped},
    )
