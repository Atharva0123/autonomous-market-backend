"""English headline sentiment primitives shared by feeds and research views.

Scores use VADER compound polarity from -1 to +1. Unsupported languages and
missing publication times remain explicitly unavailable rather than guessed.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_ANALYZER = SentimentIntensityAnalyzer()
_ENGLISH = {"en", "eng", "english"}


def score_english_headline(text: str, language: str | None) -> float | None:
    """Return a clamped English VADER score, or None for unsupported language."""
    if (language or "").strip().casefold() not in _ENGLISH or not text.strip():
        return None
    return max(-1.0, min(1.0, float(_ANALYZER.polarity_scores(text)["compound"])))


def sentiment_label(score: float | None) -> str:
    """Map a normalized compound score to its human-readable sentiment label."""
    if score is None:
        return "unavailable"
    return "positive" if score >= 0.15 else "negative" if score <= -0.15 else "neutral"


def aggregate_headline_sentiment(stories: Iterable[Any], days: int,
                                 now: datetime | None = None) -> dict[str, Any]:
    """Compute an equally weighted score for dated, scored stories in a window."""
    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(days=days)
    eligible: list[float] = []
    for story in stories:
        score = getattr(story, "sentiment_score", None)
        published = getattr(story, "published_at", None)
        if score is None or published is None:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if cutoff <= published <= moment + timedelta(hours=1):
            eligible.append(float(score))
    value = sum(eligible) / len(eligible) if eligible else None
    return {"score": value, "label": sentiment_label(value), "evidence_count": len(eligible),
            "window_days": days, "as_of": moment.isoformat(),
            "method": "Unweighted mean of English VADER headline compound scores"}
