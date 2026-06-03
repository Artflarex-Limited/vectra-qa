"""
Robust JSON extraction from LLM markdown output.

Handles nested code blocks, malformed output, and fallback strategies.

Usage:
    from mcp_server.json_extractor import extract_json

    json_obj = extract_json(markdown_text)
"""

import json
import re
from typing import Any, Dict, Optional, cast

import structlog

logger = structlog.get_logger()


def _try_repair_json(candidate: str) -> Optional[Dict[str, Any]]:
    """
    Parse a JSON candidate, applying common LLM output repairs when the
    direct parse fails: smart quotes, trailing commas, JS-style comments.

    Returns the parsed value on success, None if every attempt fails.
    """
    if not candidate or not candidate.strip():
        return None

    # Direct parse handles the common valid-JSON case without any repair cost.
    try:
        return cast(Dict[str, Any], json.loads(candidate))
    except json.JSONDecodeError:
        pass

    # Cumulative repairs: each transform runs on the output of the previous.
    # Order is safe because we only enter this branch when the raw text is
    # already invalid; over-repairing is a non-issue for any input that
    # json.loads would otherwise accept.
    repaired = candidate
    repaired = re.sub(r"/\*.*?\*/", "", repaired, flags=re.DOTALL)  # /* block */ comments
    repaired = re.sub(r"//[^\n]*", "", repaired)  # // line comments
    repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')  # " " smart double quotes
    repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")  # ' ' smart single quotes
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)  # trailing commas

    try:
        return cast(Dict[str, Any], json.loads(repaired))
    except json.JSONDecodeError:
        return None


def _find_balanced_segment(text: str, start: int, open_char: str, close_char: str) -> int:
    """
    Find the exclusive end index of the balanced segment that starts at
    `start` with `open_char`. Respects JSON string boundaries and escapes
    so braces/brackets inside string literals do not affect the count.

    Returns -1 when no balanced close is found before end of text.
    """
    count = 0
    in_string = False
    escape_next = False

    for i, char in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"' and not in_string:
            in_string = True
        elif char == '"' and in_string:
            in_string = False
            continue
        if in_string:
            continue
        if char == open_char:
            count += 1
        elif char == close_char:
            count -= 1
            if count == 0:
                return i + 1

    return -1


def extract_json(
    text: str,
    fallback: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extract JSON from markdown text with multiple fallback strategies.

    Strategies (in order):
    1. Extract from ```json code block
    2. Extract from ``` code block (any language)
    3. Find first valid JSON object/array in text
    4. Return fallback
    """
    if not text or not text.strip():
        return fallback or {}

    text = text.strip()

    # Strategy 1: ```json block
    json_match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if json_match:
        try:
            return cast(Dict[str, Any], json.loads(json_match.group(1).strip()))
        except json.JSONDecodeError:
            pass

    # Strategy 2: ``` block (any language)
    code_match = re.search(r"```\w*\s*\n(.*?)\n```", text, re.DOTALL)
    if code_match:
        try:
            return cast(Dict[str, Any], json.loads(code_match.group(1).strip()))
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find first valid JSON object (with repair fallback)
    for match in re.finditer(r"\{", text):
        start = match.start()
        segment_end = _find_balanced_segment(text, start, "{", "}")
        if segment_end <= 0:
            continue
        repaired = _try_repair_json(text[start:segment_end])
        if repaired is not None:
            return cast(Dict[str, Any], repaired)
        # Repair failed: re.finditer advances to the next { and we try again.

    # Strategy 4: Find first valid JSON array (with repair fallback)
    for match in re.finditer(r"\[", text):
        start = match.start()
        segment_end = _find_balanced_segment(text, start, "[", "]")
        if segment_end <= 0:
            continue
        repaired = _try_repair_json(text[start:segment_end])
        if repaired is not None:
            return cast(Dict[str, Any], repaired)
        # Repair failed: re.finditer advances to the next [ and we try again.

    # Fallback: return `fallback` as-is so an explicit `None` is honored.
    # Callers that pass `fallback=None` get `None` back, which lets them
    # distinguish "no JSON extracted" from "extracted an empty dict".
    logger.warning("json_extraction_failed", text_preview=text[:200])
    return fallback
