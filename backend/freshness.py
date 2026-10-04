"""Detect research topics that should bypass cached reports."""

import re


FRESHNESS_PATTERNS = [
    r"\btoday\b",
    r"\btoday's\b",
    r"\btonight\b",
    r"\bnow\b",
    r"\blive\b",
    r"\breal[-\s]?time\b",
    r"\bbreaking\b",
    r"\blatest\b",
    r"\bcurrent\b",
    r"\brecent\b",
    r"\bnew\b",
    r"\bnews\b",
    r"\bheadline[s]?\b",
    r"\bthis\s+(week|month|year|morning|evening)\b",
    r"\blast\s+(24\s+hours|hour|week|month)\b",
    r"\bweather\b",
    r"\bstock\s+(price|market)\b",
    r"\bmarket\s+(today|now|update)\b",
    r"\belection\s+(result|results|update|updates|poll|polls)\b",
    r"\bscore[s]?\b",
    r"\bmatch\s+(result|score|update)\b",
]


def is_freshness_sensitive(topic: str) -> bool:
    text = (topic or "").strip().lower()
    return any(re.search(pattern, text) for pattern in FRESHNESS_PATTERNS)


def should_use_cache(topic: str, force_fresh: bool = False) -> bool:
    return not force_fresh and not is_freshness_sensitive(topic)

