"""Site classification using HTTP fetch + DOM heuristics + LLM.

This module provides :class:`SiteClassifier`, which fetches a URL,
extracts lightweight DOM signals, runs a fast regex heuristic, and
calls an LLM for a final classification. The heuristic layer guards
against LLM hallucination; the LLM layer catches patterns the regex
cannot express.
"""

from __future__ import annotations

import asyncio
import re
from typing import Dict, List, Optional, Tuple

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from .site_catalog import SiteType

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex helpers — compiled once at import time.
# ---------------------------------------------------------------------------
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<(form|input|button|a)\b[^>]*>", re.IGNORECASE)

# Heuristic patterns mapped to site-type confidence bumps.
_HEURISTIC_PATTERNS: Dict[SiteType, re.Pattern] = {
    SiteType.ECOMMERCE: re.compile(
        r"cart_count|add[-_]to[-_]cart|product-|price-", re.IGNORECASE
    ),
    SiteType.BLOG: re.compile(
        r"post-|article-|entry-", re.IGNORECASE
    ),
    SiteType.SAAS_APP: re.compile(
        r"dashboard|chart-|data-table", re.IGNORECASE
    ),
}

OVERRIDE_ALIASES: Dict[str, SiteType] = {
    "blog": SiteType.BLOG,
    "e-commerce": SiteType.ECOMMERCE,
    "ecommerce": SiteType.ECOMMERCE,
    "landing": SiteType.LANDING,
    "saas": SiteType.SAAS_APP,
    "saas_app": SiteType.SAAS_APP,
    "portal": SiteType.PORTAL,
}


class ClassificationResult(BaseModel):
    """Immutable result of a site classification."""

    site_type: SiteType
    confidence: float = Field(..., ge=0.0, le=1.0)
    signals: List[str]

    model_config = ConfigDict(extra="forbid")


def _extract_title(html: str) -> str:
    match = _TITLE_RE.search(html)
    return match.group(1).strip() if match else ""


def _extract_body_snippet(html: str, max_bytes: int = 5120) -> str:
    match = _BODY_RE.search(html)
    body = match.group(1) if match else html
    return body[:max_bytes]


def _extract_selectors(html: str) -> List[str]:
    """Return a list of CSS-like selectors for <form>, <input>, <button>, <a>."""
    selectors: List[str] = []
    for match in _TAG_RE.finditer(html):
        tag = match.group(1).lower()
        attrs = match.group(0)
        id_match = re.search(r'\bid=["\']?([^"\']+)["\']?', attrs, re.IGNORECASE)
        class_match = re.search(
            r'\bclass=["\']?([^"\']+)["\']?', attrs, re.IGNORECASE
        )
        if id_match:
            selectors.append(f"#{id_match.group(1).split()[0]}")
        elif class_match:
            first_cls = class_match.group(1).split()[0]
            selectors.append(f"{tag}.{first_cls}")
        else:
            selectors.append(tag)
    return selectors


def _run_heuristics(html_text: str) -> Tuple[Dict[SiteType, float], List[str]]:
    """Return (scores, signal_descriptions)."""
    scores: Dict[SiteType, float] = {st: 0.0 for st in SiteType}
    signals: List[str] = []
    for site_type, pattern in _HEURISTIC_PATTERNS.items():
        if pattern.search(html_text):
            scores[site_type] = 0.4
            signals.append(f"heuristic:{site_type.value}")
    return scores, signals


def _parse_llm_response(raw: str) -> Tuple[Optional[SiteType], float]:
    """Parse the LLM response for a site type and confidence."""
    raw_upper = raw.upper()
    detected_type: Optional[SiteType] = None
    for st in SiteType:
        if st.name in raw_upper:
            detected_type = st
            break

    conf_match = re.search(
        r"confidence\s*[:=]?\s*([0-9]*\.?[0-9]+)", raw, re.IGNORECASE
    )
    confidence = 0.0
    if conf_match:
        confidence = float(conf_match.group(1))
        confidence = max(0.0, min(1.0, confidence))

    return detected_type, confidence


class SiteClassifier:
    """Classify a web site into one of the :class:`SiteType` archetypes."""

    def __init__(self, llm=None):
        if llm is None:
            from mcp_server.llm_router import llm_router

            llm = llm_router
        self.llm = llm

    async def classify(
        self,
        url: str,
        session: Optional[httpx.AsyncClient] = None,
    ) -> ClassificationResult:
        logger.info("classifying_url", url=url)

        # 1. Fetch URL with 10 s timeout.
        if session is not None:
            response = await asyncio.wait_for(session.get(url), timeout=10.0)
        else:
            async with httpx.AsyncClient(
                timeout=10.0, follow_redirects=True
            ) as client:
                response = await asyncio.wait_for(client.get(url), timeout=10.0)

        html = response.text

        # 2. Capture signals.
        title = _extract_title(html)
        body_snippet = _extract_body_snippet(html)
        selectors = _extract_selectors(html)
        selector_str = " ".join(selectors)
        html_text = f"{title} {body_snippet} {selector_str}"

        # 3. Heuristics.
        heuristic_scores, heuristic_signals = _run_heuristics(html_text)

        # 4. LLM call.
        prompt = self._build_prompt(url, title, heuristic_signals)
        llm_response = await self._call_llm(prompt)
        llm_type, llm_confidence = _parse_llm_response(llm_response)

        # 5. Merge heuristic + LLM.
        final_type, final_confidence, all_signals = self._merge(
            heuristic_scores,
            heuristic_signals,
            llm_type,
            llm_confidence,
        )

        result = ClassificationResult(
            site_type=final_type,
            confidence=final_confidence,
            signals=all_signals,
        )
        logger.info(
            "classification_done",
            url=url,
            site_type=final_type.value,
            confidence=final_confidence,
        )
        return result

    def _build_prompt(self, url: str, title: str, signals: List[str]) -> str:
        signal_text = ", ".join(signals) if signals else "none"
        return (
            f"URL: {url}\n"
            f"Title: {title}\n"
            f"Signals: {signal_text}\n\n"
            "Classify this site into exactly one of the following types: "
            "LANDING, ECOMMERCE, BLOG, SAAS_APP, PORTAL.\n"
            "Respond with the site type name and a confidence score between 0 and 1.\n"
            "Format: TYPE (confidence: X.XX)"
        )

    async def _call_llm(self, prompt: str) -> str:
        messages = [{"role": "user", "content": prompt}]
        if asyncio.iscoroutinefunction(self.llm.complete):
            response = await self.llm.complete(
                model="openai/gpt-4o",
                messages=messages,
                temperature=0.0,
                max_tokens=64,
            )
        else:
            response = await asyncio.to_thread(
                self.llm.complete,
                model="openai/gpt-4o",
                messages=messages,
                temperature=0.0,
                max_tokens=64,
            )
        return response.content

    def _merge(
        self,
        heuristic_scores: Dict[SiteType, float],
        heuristic_signals: List[str],
        llm_type: Optional[SiteType],
        llm_confidence: float,
    ) -> Tuple[SiteType, float, List[str]]:
        candidates: Dict[SiteType, float] = dict(heuristic_scores)
        if llm_type is not None:
            candidates[llm_type] = max(
                candidates.get(llm_type, 0.0), llm_confidence
            )

        if not candidates or all(v == 0.0 for v in candidates.values()):
            return SiteType.LANDING, 0.0, heuristic_signals + ["fallback:landing"]

        final_type = max(candidates, key=lambda k: candidates[k])
        final_confidence = candidates[final_type]

        all_signals = list(heuristic_signals)
        if llm_type is not None:
            all_signals.append(f"llm:{llm_type.value}(conf={llm_confidence:.2f})")

        return final_type, final_confidence, all_signals


def validate_override(user_choice: str) -> SiteType:
    """Convert a user-friendly override string to a canonical :class:`SiteType`."""
    normalized = user_choice.strip().lower()
    if normalized in OVERRIDE_ALIASES:
        return OVERRIDE_ALIASES[normalized]
    try:
        return SiteType(normalized)
    except ValueError:
        pass
    raise ValueError(f"Unknown site type override: {user_choice!r}")


__all__ = [
    "ClassificationResult",
    "SiteClassifier",
    "validate_override",
]
