"""Unit tests for command_center.engineer.vocabulary (T4).

Covers FORBIDDEN_WORDS shape, scrub_forbidden detection + cleaning,
enforce_word_budget sentence-boundary truncation, glossary completeness,
and the 5-section report template.
"""
from __future__ import annotations

from command_center.engineer.vocabulary import (
    FORBIDDEN_WORDS,
    REPORT_TEMPLATE,
    VOCABULARY_GLOSSARY,
    enforce_word_budget,
    scrub_forbidden,
)


def test_vocabulary() -> None:
    """Aggregate smoke test for the T4 vocabulary module.

    Each assertion maps to one of the acceptance criteria in
    .omo/plans/live-qa-engineer.md (T4) or the plan's QA scenarios.
    """
    # --- FORBIDDEN_WORDS shape ---
    assert "selector" in FORBIDDEN_WORDS
    # plurals are present
    for plural in ("selectors", "schemas", "payloads", "viewports", "cookies"):
        assert plural in FORBIDDEN_WORDS, f"missing plural: {plural}"

    # --- scrub_forbidden: removes word, returns it in the found list ---
    cleaned, found = scrub_forbidden("The selector is broken")
    assert "selector" not in cleaned
    assert "selector" in found
    # plural detection via lowercase substring
    cleaned_p, found_p = scrub_forbidden("All the selectors are broken")
    assert "selectors" in found_p
    assert "selectors" not in cleaned_p

    # --- scrub_forbidden: case-insensitive ---
    cleaned_c, found_c = scrub_forbidden("The DOM was empty and the Jwt was wrong")
    # 'DOM' (uppercase) and 'JWT' (uppercase) should be detected
    assert any(w.upper() == "DOM" for w in found_c)
    assert any(w.upper() == "JWT" for w in found_c)

    # --- scrub_forbidden: 'console error' (multi-word) is detected ---
    cleaned_e, found_e = scrub_forbidden("a console error appeared on the page")
    assert "console error" in found_e
    assert "console error" not in cleaned_e

    # --- scrub_forbidden: empty / None-safe ---
    assert scrub_forbidden("") == ("", [])

    # --- scrub_forbidden: high-volume detection (QA scenario 1) ---
    text = (
        "The selector failed, the DOM was wrong, the JWT was invalid, "
        "the payload was empty, the viewport was 320px, the status code was 500, "
        "XHR failed, the console error appeared"
    )
    _, found = scrub_forbidden(text)
    assert len(found) >= 6

    # --- enforce_word_budget: acceptance criterion (max_words=2) ---
    assert enforce_word_budget("a. b. c. d.", max_words=2) == "a. b."

    # --- enforce_word_budget: no truncation when within budget ---
    out = enforce_word_budget("Just one sentence.", max_words=10)
    assert out == "Just one sentence."

    # --- enforce_word_budget: empty input ---
    assert enforce_word_budget("", max_words=5) == ""
    assert enforce_word_budget("some text", max_words=0) == ""

    # --- enforce_word_budget: never breaks a sentence in the middle ---
    # First sentence alone exceeds the budget — surface it rather than truncating
    # the word in half (the 'kept' guard).
    out = enforce_word_budget("This is a fairly long first sentence. Second.", max_words=2)
    # The function returns the first sentence in full because we never break
    # a sentence in the middle. wc_after_first = 6 > 2, but 'kept' is empty so
    # we still add it. Next sentence would push to 8, break. Result has 1 sentence.
    assert out.startswith("This is a fairly long first sentence.")

    # --- enforce_word_budget: stops at sentence boundary, not word boundary ---
    out = enforce_word_budget(
        "First sentence. Second sentence. Third sentence.", max_words=2
    )
    assert out == "First sentence."

    # --- glossary covers every forbidden word (QA scenario 3) ---
    missing = FORBIDDEN_WORDS - set(VOCABULARY_GLOSSARY.keys())
    assert not missing, f"missing glossary entries: {missing}"

    # --- glossary values are non-empty, plain-English, and not the original word ---
    for word, plain in VOCABULARY_GLOSSARY.items():
        assert plain.strip(), f"empty glossary entry for {word!r}"
        # The glossary should not just echo the forbidden word back.
        assert plain.lower() != word.lower(), f"glossary echo for {word!r}"

    # --- report template has 5 required sections ---
    for section in ("Summary", "What Works", "What Needs Attention",
                    "Recommendations", "Next Steps"):
        assert section in REPORT_TEMPLATE, f"missing section: {section}"

    # --- report template uses no forbidden jargon in its instructions ---
    cleaned_template, template_hits = scrub_forbidden(REPORT_TEMPLATE)
    # The template is meta-text; it should not itself contain forbidden words.
    # (If the template mentions 'CSS' or 'HTML' as part of a section name, scrub
    # would flag it. Keep the template clean by construction.)
    assert not template_hits, f"template contains forbidden words: {template_hits}"


def test_scrub_returns_ordered_unique_offenders() -> None:
    """scrub_forbidden returns a deterministic, de-duplicated list."""
    _, found = scrub_forbidden("selector selector selector")
    assert found.count("selector") == 1


def test_enforce_word_budget_preserves_trailing_punctuation() -> None:
    """The function never strips the final period/exclamation/question mark."""
    assert enforce_word_budget("Hello world.", max_words=2) == "Hello world."
    assert enforce_word_budget("Wow! That worked.", max_words=5) == "Wow! That worked."
