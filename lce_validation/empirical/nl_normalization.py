from __future__ import annotations

import re


ALIASES = {
    "listening": "port",
    "endpoint": "port",
    "number": "port",
    "assigned": "port",
    "uses": "use",
    "using": "use",
    "replace": "replacement",
    "replacing": "replacement",
    "enough": "prove",
    "right": "current",
    "now": "current",
    "currently": "current",
    "go": "proceed",
    "ahead": "proceed",
    "sign": "approval",
    "off": "approval",
}

STOPWORDS = {
    "a",
    "an",
    "the",
    "to",
    "for",
    "of",
    "on",
    "in",
    "is",
    "are",
    "am",
    "be",
    "this",
    "that",
    "me",
    "you",
    "can",
    "could",
    "would",
    "should",
    "please",
    "tell",
    "find",
}


def normalize_tokens(text: str) -> list[str]:
    raw = [tok for tok in re.findall(r"[A-Za-z0-9_]+", text.lower()) if len(tok) > 1]
    tokens: list[str] = []
    for token in raw:
        if token in STOPWORDS:
            continue
        canonical = ALIASES.get(token, token)
        tokens.append(canonical)
    return tokens
