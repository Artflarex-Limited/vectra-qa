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


def extract_json(text: str, fallback: Optional[Dict] = None) -> Dict[str, Any]:
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

    # Strategy 3: Find first valid JSON object
    # Look for balanced braces
    for match in re.finditer(r"\{", text):
        start = match.start()
        brace_count = 0
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
            elif not in_string:
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        try:
                            return cast(Dict[str, Any], json.loads(text[start : i + 1]))
                        except json.JSONDecodeError:
                            break

    # Strategy 4: Find first valid JSON array
    for match in re.finditer(r"\[", text):
        start = match.start()
        bracket_count = 0
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
            elif not in_string:
                if char == "[":
                    bracket_count += 1
                elif char == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        try:
                            return cast(Dict[str, Any], json.loads(text[start : i + 1]))
                        except json.JSONDecodeError:
                            break

    # Fallback
    logger.warning("json_extraction_failed", text_preview=text[:200])
    return fallback or {}
