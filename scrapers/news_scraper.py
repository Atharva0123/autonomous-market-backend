"""Parse public RSS news as a resilient fallback for a throttled news API.

This module only consumes the publisher index's public RSS feed. It does not
bypass logins, CAPTCHAs, robots controls, or provider access restrictions.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx
from api.models import NewsStory, SourceCitation
from components.sentiment_gauge import score_english_headline, sentiment_label

logger = logging.getLogger(__name__)
MAX_FEED_BYTES = 2_000_000
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"


def parse_public_news_rss(payload: bytes | str, country_iso3: str, topic: str,
                          limit: int = 30, retrieved_at: datetime | None = None) -> list[NewsStory]:
    """Parse a bounded RSS response into normalized, source-linked stories."""
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if len(raw) > MAX_FEED_BYTES:
        raise ValueError("News RSS response exceeded the 2 MB safety limit.")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        logger.warning("Public news RSS could not be parsed: %s", exc)
        raise ValueError("The public news feed returned malformed XML.") from exc
    fetched = retrieved_at or datetime.now(timezone.utc)
    stories: list[NewsStory] = []
    for item in root.findall(".//item")[:min(max(limit, 1), 100)]:
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        if not title or not url.startswith(("https://", "http://")):
            continue
        publisher = (item.findtext("source") or "Google News indexed publisher").strip()[:160]
        published = _parse_date(item.findtext("pubDate"))
        score = score_english_headline(title, "English")
        stories.append(NewsStory(
            title=title[:400], url=url, publisher=publisher, published_at=published,
            language="English", country_iso3=country_iso3.upper(), topic=topic,
            sentiment_score=score, sentiment_label=sentiment_label(score),
            sentiment_evidence_count=1 if score is not None else 0,
            sentiment_model="VADER compound · English headline only" if score is not None else None,
            source=SourceCitation(
                source_id="google-news-rss", name=publisher, url=url,
                dataset="Google News RSS", record_id=url, retrieved_at=fetched,
                observed_at=published.isoformat() if published else None,
                cadence="news-index dependent", status="available",
                usage_note="Indexed third-party publisher headline; verify the linked publisher source.")))
    return stories


async def fetch_public_news_rss(query: str, country_iso3: str = "WLD",
                               limit: int = 8) -> list[NewsStory]:
    """Fetch a public RSS search result with strict timeout and response bounds."""
    cleaned = query.strip()[:180]
    if not cleaned:
        raise ValueError("Enter a short news topic before testing the RSS scraper.")
    params = {"q": cleaned, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    url = f"{GOOGLE_NEWS_RSS_URL}?{urlencode(params)}"
    timeout = httpx.Timeout(8.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                                 headers={"User-Agent": "MarketIntelligenceDesk/1.0 (public RSS fallback)"}) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_FEED_BYTES:
                raise ValueError("News RSS response exceeded the 2 MB safety limit.")
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_FEED_BYTES:
                    raise ValueError("News RSS response exceeded the 2 MB safety limit.")
                chunks.append(chunk)
    return parse_public_news_rss(b"".join(chunks), country_iso3, cleaned, limit=limit)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
