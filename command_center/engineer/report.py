"""Plain-English report builder for the live QA engineer.

Aggregates raw agent findings by severity, asks the LLM to produce a
structured 5-section report, scrubs forbidden jargon, enforces the 150-word
per-section budget, and returns a :class:`ReportEvent`.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from command_center.engineer.events import ReportEvent
from command_center.engineer.vocabulary import (
    REPORT_TEMPLATE,
    enforce_word_budget,
    scrub_forbidden,
)
from mcp_server.llm_router import llm_router

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Severity → plain-English mapping
# ---------------------------------------------------------------------------

_SEVERITY_LABELS: Dict[str, str] = {
    "critical": "needs immediate attention",
    "high": "should fix soon",
    "medium": "worth fixing",
    "low": "minor polish",
    "info": "good to know",
}

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def severity_color(severity: str) -> str:
    """Map a technical severity label to plain English.

    >>> severity_color("critical")
    'needs immediate attention'
    """
    return _SEVERITY_LABELS.get(severity.lower(), severity)


def recommendation_actionability_check(rec: str) -> bool:
    """Heuristic: does the recommendation contain an action verb?

    For the MVP we return ``True`` if any of the known action verbs appears
    in the text.  A future iteration could enforce verb+noun pairing.
    """
    action_verbs = {
        "fix",
        "add",
        "remove",
        "change",
        "update",
        "replace",
        "configure",
        "set",
        "make",
    }
    rec_lower = rec.lower()
    return any(verb in rec_lower for verb in action_verbs)


# ---------------------------------------------------------------------------
# ReportBuilder
# ---------------------------------------------------------------------------


class ReportBuilder:
    """Builds a plain-English :class:`ReportEvent` from raw agent findings."""

    def __init__(self, llm: Optional[Any] = None):
        self.llm = llm or llm_router

    async def build_report(
        self,
        session_id: str,
        agent_findings: List[Dict[str, Any]],
        stage: str = "report",
    ) -> ReportEvent:
        """Aggregate findings, call the LLM, scrub, budget, and return a ``ReportEvent``."""
        # --- 1. aggregate by severity ---------------------------------------
        severity_groups: Dict[str, List[Dict[str, Any]]] = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
            "info": [],
        }
        for finding in agent_findings:
            sev = str(finding.get("severity", "info")).lower()
            severity_groups.setdefault(sev, []).append(finding)
            if sev not in severity_groups:
                severity_groups["info"].append(finding)

        # Build a plain-English context block for the LLM prompt.
        context_lines: List[str] = []
        for sev in ("critical", "high", "medium", "low", "info"):
            items = severity_groups.get(sev, [])
            if not items:
                continue
            label = severity_color(sev)
            context_lines.append(f"\n{label} ({len(items)}):")
            for item in items:
                title = item.get("title", "")
                desc = item.get("description", "")
                if desc:
                    context_lines.append(f"  - {title}: {desc}")
                else:
                    context_lines.append(f"  - {title}")
        context = "\n".join(context_lines)

        # --- 2. build prompt ------------------------------------------------
        prompt = f"""You are a QA engineer writing a summary for a non-technical stakeholder.
Use only plain English. Avoid technical jargon. 150 words or fewer per section.
Use this template:

{REPORT_TEMPLATE}

Based on the following findings, fill in all 5 sections:

{context}

Write the complete report now with all 5 sections clearly marked."""

        # --- 3. call LLM ----------------------------------------------------
        try:
            response = await self.llm.complete(
                model="anthropic/claude-3-5-sonnet-20241022",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a QA engineer writing plain-English reports. "
                            "Avoid technical jargon. Keep each section concise."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2500,
            )
            content: str = response.content
        except Exception as exc:  # pragma: no cover
            logger.debug("report_generation_fallback", error=str(exc))
            content = (
                "# Summary\n"
                "Report generation encountered an error.\n"
                "# What Works\n"
                "- N/A\n"
                "# What Needs Attention\n"
                "- N/A\n"
                "# Recommendations\n"
                "1. Retry report generation.\n"
                "# Next Steps\n"
                "- Investigate the error.\n"
            )

        # --- 4. parse 5 sections --------------------------------------------
        raw_sections = self._parse_sections(content)

        # --- 5. scrub + budget ----------------------------------------------
        cleaned_sections: Dict[str, str] = {}
        for section_name in (
            "Summary",
            "What Works",
            "What Needs Attention",
            "Recommendations",
            "Next Steps",
        ):
            raw = raw_sections.get(section_name, "")
            scrubbed, _ = scrub_forbidden(raw)
            budgeted = enforce_word_budget(scrubbed, 150)
            # Fallback: if a single sentence exceeds the budget,
            # enforce_word_budget surfaces it rather than truncating.
            # We hard-cap at 150 words so downstream consumers never
            # receive over-budget text.
            words = budgeted.split()
            if len(words) > 150:
                budgeted = " ".join(words[:150]) + "."
            cleaned_sections[section_name] = budgeted

        timestamp = datetime.now(timezone.utc).isoformat()
        return ReportEvent(
            session_id=session_id,
            stage=stage,
            timestamp=timestamp,
            sections=cleaned_sections,
        )

    def _parse_sections(self, content: str) -> Dict[str, str]:
        """Parse the 5 standard report sections from markdown content.

        Matches ``# Section Name`` or ``## Section Name`` at the start of a
        line (case-insensitive) and captures everything up to the next
        recognised header.
        """
        sections: Dict[str, str] = {}
        section_names = [
            "Summary",
            "What Works",
            "What Needs Attention",
            "Recommendations",
            "Next Steps",
        ]

        for i, name in enumerate(section_names):
            if i < len(section_names) - 1:
                next_name = section_names[i + 1]
                pattern = (
                    rf"(?:^|\n)#+\s*{re.escape(name)}\s*\n"
                    rf"(.*?)"
                    rf"(?=(?:^|\n)#+\s*{re.escape(next_name)}\s*(?:\n|$))"
                )
            else:
                pattern = rf"(?:^|\n)#+\s*{re.escape(name)}\s*\n(.*)"

            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                sections[name] = match.group(1).strip()
            else:
                sections[name] = ""

        return sections


__all__ = [
    "ReportBuilder",
    "severity_color",
    "recommendation_actionability_check",
]
