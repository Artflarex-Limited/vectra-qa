"""Plain-English vocabulary and report template for the live QA engineer.

This module prevents the LLM from leaking technical jargon into user-facing
reports and narration. It is the only authority for what counts as
"jargon" inside the command center.

Exports
-------
FORBIDDEN_WORDS
    Set of technical terms the LLM must avoid (singular + plural forms).
VOCABULARY_GLOSSARY
    Plain-English substitutes; used as a system-prompt hint, not auto-applied.
REPORT_TEMPLATE
    5-section report skeleton with per-section word budgets.
scrub_forbidden(text)
    Strip forbidden words from ``text`` and return the list that were found.
enforce_word_budget(text, max_words)
    Truncate ``text`` at the nearest sentence boundary that fits the budget.

Design notes
------------
* ``scrub_forbidden`` is intentionally **loud**: it does NOT silently
  substitute jargon with a plain-English phrase. The caller (the orchestrator
  or the test runner) decides what to do with the offender list — typically
  ask the LLM to rewrite. Hiding the LLM's mistake would defeat the point.
* The glossary is exported as data, not behavior. Inject it into the system
  prompt so the LLM self-corrects; never use it as a blind ``str.replace``.
* ``enforce_word_budget`` never breaks a sentence in the middle — that would
  produce truncated, unreadable output.
"""
from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

# ---------------------------------------------------------------------------
# Forbidden jargon — base forms (singular / single-token)
# ---------------------------------------------------------------------------
_BASE_FORBIDDEN: Set[str] = {
    "selector",
    "DOM",
    "viewport",
    "breakpoint",
    "JWT",
    "payload",
    "schema",
    "XHR",
    "fetch",
    "console error",
    "404",
    "500",
    "status code",
    "CSS",
    "HTML",
    "click handler",
    "event listener",
    "cookie",
    "session ID",
}

# Plural / variant forms. The single substring check in ``scrub_forbidden``
# catches both the base and the plural with the same code path.
_PLURALS: Set[str] = {
    "selectors",
    "viewports",
    "breakpoints",
    "payloads",
    "schemas",
    "fetches",
    "console errors",
    "status codes",
    "click handlers",
    "event listeners",
    "cookies",
    "session IDs",
}

FORBIDDEN_WORDS: Set[str] = _BASE_FORBIDDEN | _PLURALS


# ---------------------------------------------------------------------------
# Plain-English glossary — system-prompt hint, not auto-replace
# ---------------------------------------------------------------------------
VOCABULARY_GLOSSARY: Dict[str, str] = {
    "selector": "part of the page",
    "selectors": "parts of the page",
    "DOM": "the page content",
    "viewport": "the visible screen area",
    "viewports": "the visible screen areas",
    "breakpoint": "screen size threshold",
    "breakpoints": "screen size thresholds",
    "JWT": "login token",
    "payload": "data packet",
    "payloads": "data packets",
    "schema": "data shape",
    "schemas": "data shapes",
    "XHR": "old-style web request",
    "fetch": "request to the server",
    "fetches": "requests to the server",
    "console error": "developer message about a problem",
    "console errors": "developer messages about problems",
    "404": "page not found error",
    "500": "server-side error",
    "status code": "response number from the server",
    "status codes": "response numbers from the server",
    "CSS": "styling rules",
    "HTML": "page markup",
    "click handler": "the action triggered when something is clicked",
    "click handlers": "the actions triggered when things are clicked",
    "event listener": "background watcher for user actions",
    "event listeners": "background watchers for user actions",
    "cookie": "small browser tracker",
    "cookies": "small browser trackers",
    "session ID": "login identifier",
    "session IDs": "login identifiers",
}


# ---------------------------------------------------------------------------
# Report template — no jargon, no code blocks
# ---------------------------------------------------------------------------
REPORT_TEMPLATE: str = """# Test Report

## Summary
Write a short overview in plain English (target: 150 words or fewer). Cover
what was tested, the overall outcome, and any urgent concerns a non-technical
reader needs to know. Avoid code, error numbers, and library names.

## What Works
- Describe a part of the app that behaved correctly, in plain English.
- Describe another part that behaved correctly, in plain English.
- Describe a third part that behaved correctly, in plain English.

## What Needs Attention
- [Severity: High] Plain-English description of the most important issue.
- [Severity: Medium] Plain-English description of a second issue.
- [Severity: Low] Plain-English description of a minor issue.

## Recommendations
1. First recommendation, written for a product or business reader.
2. Second recommendation in the same tone.
3. Third recommendation in the same tone.
(Five is the hard cap — do not add more.)

## Next Steps
- First concrete next step, in plain English.
- Second concrete next step, in plain English.
(Three is the hard cap — do not add more.)
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def scrub_forbidden(text: str) -> Tuple[str, List[str]]:
    """Strip forbidden jargon from ``text`` and return the words that were found.

    The scrubber is intentionally **loud**: it does NOT silently substitute
    forbidden words with a plain-English equivalent. Instead it removes them
    from the text and returns the list of offenders so the caller can decide
    how to handle the LLM's mistake (reject, retry, rewrite, etc.).

    Plural detection is handled by lower-casing both sides of a ``re.search``
    substring match — the same code path that catches "selector" also catches
    "selectors" because ``selectors`` is a substring of itself in lower case.
    """
    if not text:
        return "", []

    text_lower = text.lower()
    found: List[str] = []
    for word in FORBIDDEN_WORDS:
        if re.search(re.escape(word.lower()), text_lower):
            found.append(word)

    cleaned = text
    for word in found:
        cleaned = re.sub(re.escape(word), "", cleaned, flags=re.IGNORECASE)
    # Tidy up the gaps left by removed words — collapse spaces, keep punctuation.
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    cleaned = cleaned.strip()
    return cleaned, found


def enforce_word_budget(text: str, max_words: int) -> str:
    """Truncate ``text`` to at most ``max_words`` words, ending at a sentence boundary.

    Sentences are split on the ``". "`` separator. The function never breaks
    a sentence in the middle; if adding the next sentence would push the
    running total over the budget, the loop stops and the already-kept
    sentences are returned.
    """
    if not text or max_words <= 0:
        return ""

    sentences = text.split(". ")
    kept: List[str] = []
    word_count = 0
    last_index = len(sentences) - 1

    for i, sent in enumerate(sentences):
        # Re-attach a period to non-final segments; the final segment keeps
        # its own trailing punctuation (or gains a period if missing).
        if i < last_index:
            sent_text = sent + "."
        else:
            sent_text = sent if sent.endswith((".", "!", "?")) else sent + "."

        words = sent_text.split()
        # ``kept`` guard: never produce an empty result if the first sentence
        # alone exceeds the budget — surface it so the caller knows the input
        # was unsalvageable rather than returning an empty string silently.
        if word_count + len(words) > max_words and kept:
            break
        kept.append(sent_text)
        word_count += len(words)

    return " ".join(kept)


__all__ = [
    "FORBIDDEN_WORDS",
    "VOCABULARY_GLOSSARY",
    "REPORT_TEMPLATE",
    "scrub_forbidden",
    "enforce_word_budget",
]
