"""
Unit tests for the hardened JSON extractor (mcp_server.json_extractor).

Locks in the multi-strategy parser behavior:
- Strategy 1: ```json fenced blocks
- Strategy 2: generic ``` fenced blocks
- Strategy 3: raw JSON object embedded in prose
- Strategy 4: raw JSON array fallback
- Repairs: trailing commas, smart quotes, JS-style comments
- Recovery: continue past malformed candidates to find valid JSON
- Safety: truncated input must not hang
- Fallback: explicit None is honored; default is {}
"""

import pytest

from mcp_server.json_extractor import extract_json


# ---------------------------------------------------------------------------
# Smart-quote constants — explicit Unicode for clarity
# ---------------------------------------------------------------------------

LEFT_SMART_QUOTE = "\u201c"   # "
RIGHT_SMART_QUOTE = "\u201d"  # "


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractJson:
    """Tests for robust JSON extraction from LLM output."""

    # ------------------------------------------------------------------
    # Strategy 1: ```json fenced blocks
    # ------------------------------------------------------------------
    @pytest.mark.unit
    def test_json_fenced_block_parses(self):
        text = '```json\n{"action": "click", "selector": "#btn"}\n```'
        assert extract_json(text) == {"action": "click", "selector": "#btn"}

    # ------------------------------------------------------------------
    # Strategy 2: generic fenced blocks
    # ------------------------------------------------------------------
    @pytest.mark.unit
    def test_unfenced_code_block_parses(self):
        text = '```\n{"action": "click"}\n```'
        assert extract_json(text) == {"action": "click"}

    # ------------------------------------------------------------------
    # Strategy 3: raw JSON object in text
    # ------------------------------------------------------------------
    @pytest.mark.unit
    def test_raw_json_in_text_parses(self):
        text = 'preamble text {"action": "click", "value": 42} trailing'
        assert extract_json(text) == {"action": "click", "value": 42}

    # ------------------------------------------------------------------
    # Strategy 4: array fallback
    # ------------------------------------------------------------------
    @pytest.mark.unit
    def test_array_fallback_parses(self):
        text = 'no object here [1, 2, 3] but this is an array'
        assert extract_json(text) == [1, 2, 3]

    # ------------------------------------------------------------------
    # Trailing-comma repair
    # ------------------------------------------------------------------
    @pytest.mark.unit
    def test_trailing_comma_in_object_repaired(self):
        text = '```json\n{"a": 1, "b": 2,}\n```'
        assert extract_json(text) == {"a": 1, "b": 2}

    @pytest.mark.unit
    def test_trailing_comma_in_array_repaired(self):
        text = '```json\n[1, 2, 3,]\n```'
        assert extract_json(text) == [1, 2, 3]

    # ------------------------------------------------------------------
    # Smart-quote repair
    # ------------------------------------------------------------------
    @pytest.mark.unit
    def test_smart_double_quotes_repaired(self):
        text = (
            "```json\n"
            '{"a": ' + LEFT_SMART_QUOTE + "hello" + RIGHT_SMART_QUOTE + ', "b": 2}\n'
            "```"
        )
        assert extract_json(text) == {"a": "hello", "b": 2}

    # ------------------------------------------------------------------
    # Recovery past malformed JSON
    # ------------------------------------------------------------------
    @pytest.mark.unit
    def test_recovery_past_malformed_object(self):
        """First object is malformed, second is valid - should return second."""
        text = '{"bad": ,} then {"good": 42}'
        assert extract_json(text) == {"good": 42}

    # ------------------------------------------------------------------
    # JS-style comment removal
    # ------------------------------------------------------------------
    @pytest.mark.unit
    def test_js_line_comment_removed(self):
        text = '```json\n{"a": 1, // comment\n"b": 2}\n```'
        assert extract_json(text) == {"a": 1, "b": 2}

    @pytest.mark.unit
    def test_js_block_comment_removed(self):
        text = '```json\n{"a": 1, /* comment */ "b": 2}\n```'
        assert extract_json(text) == {"a": 1, "b": 2}

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------
    @pytest.mark.unit
    def test_empty_string_returns_fallback(self):
        assert extract_json("") == {}
        assert extract_json("   ") == {}

    @pytest.mark.unit
    def test_fallback_parameter(self):
        assert extract_json("nothing here", fallback={"x": 0}) == {"x": 0}
        assert extract_json("nothing here", fallback=None) is None

    @pytest.mark.unit
    def test_braces_inside_string_preserved(self):
        text = '{"a": "hello {world}"}'
        assert extract_json(text) == {"a": "hello {world}"}

    @pytest.mark.unit
    def test_nested_object(self):
        text = '{"a": {"b": {"c": 1}}}'
        assert extract_json(text) == {"a": {"b": {"c": 1}}}

    # ------------------------------------------------------------------
    # Realistic LLM response shapes
    # ------------------------------------------------------------------
    @pytest.mark.unit
    def test_minimax_chatty_response(self):
        """Realistic MiniMax response with preamble + fence + reasoning."""
        text = """Based on the page state, the next action is to click the login button.

```json
{
  "action": "click",
  "selector": "a:has-text('Giriş Yap')",
  "reasoning": "Test login flow",
  "expected_result": "Login modal appears",
  "confidence": 85
}
```"""
        result = extract_json(text)
        assert result["action"] == "click"
        assert result["selector"] == "a:has-text('Giriş Yap')"
        assert result["confidence"] == 85

    @pytest.mark.unit
    def test_truncated_response_does_not_hang(self):
        """Truncated JSON should not cause infinite loops."""
        text = '```json\n{"action": "click", "reasoning": "incomp'
        result = extract_json(text, fallback=None)
        # Should return None or empty - NOT raise or hang
        assert result is None or result == {}
