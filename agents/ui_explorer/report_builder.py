#!/usr/bin/env python3
"""
Report Builder for Vectra QA UI Explorer

Generates detailed, structured test reports with sections for:
- Executive Summary
- Page Information
- Navigation Audit
- Content Structure
- Form Validation
- Accessibility Check
- Responsive Design
- Performance Metrics
- Security Check
- Recommendations
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field


@dataclass
class ReportSection:
    """A section in the test report."""

    title: str
    status: str  # pass, fail, warning, info
    findings: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    details: str = ""


@dataclass
class TestReport:
    """Complete test report."""

    test_type: str
    url: str
    start_time: str
    end_time: Optional[str] = None
    overall_status: str = "pending"
    sections: List[ReportSection] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert report to markdown for memory node."""
        md = f"""# 📊 Test Report: {self.test_type.title()}

## Executive Summary

**Overall Status**: {'✅ PASS' if self.overall_status == 'pass' else '❌ FAIL' if self.overall_status == 'fail' else '⚠️ WARNING'}
**Target URL**: {self.url}
**Started**: {self.start_time}
**Completed**: {self.end_time or 'In progress...'}
"""

        # Summary table
        pass_count = sum(1 for s in self.sections if s.status == "pass")
        fail_count = sum(1 for s in self.sections if s.status == "fail")
        warn_count = sum(1 for s in self.sections if s.status == "warning")

        md += f"""
### Summary
| Metric | Value |
|--------|-------|
| Sections Passed | {pass_count} |
| Sections Failed | {fail_count} |
| Warnings | {warn_count} |
| Total Checks | {len(self.sections)} |

"""

        # Sections
        for section in self.sections:
            icon = {"pass": "✅", "fail": "❌", "warning": "⚠️", "info": "ℹ️"}.get(
                section.status, "➡️"
            )
            md += f"""## {icon} {section.title}

"""
            if section.metrics:
                md += "### Metrics\n"
                for key, value in section.metrics.items():
                    md += f"- **{key}**: {value}\n"
                md += "\n"

            if section.findings:
                md += "### Findings\n"
                for finding in section.findings:
                    severity = finding.get("severity", "info")
                    icon = {
                        "critical": "🔴",
                        "high": "🟠",
                        "medium": "🟡",
                        "low": "🔵",
                        "info": "⚪",
                    }.get(severity, "⚪")
                    md += f"- {icon} **{finding.get('title', 'Finding')}**: {finding.get('description', '')}\n"
                md += "\n"

            if section.details:
                md += f"### Details\n{section.details}\n\n"

        # Recommendations
        if self.recommendations:
            md += "## 📝 Recommendations\n\n"
            for i, rec in enumerate(self.recommendations, 1):
                md += f"{i}. {rec}\n"
            md += "\n"

        return md

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "test_type": self.test_type,
            "url": self.url,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "overall_status": self.overall_status,
            "sections": [
                {"title": s.title, "status": s.status, "findings": s.findings, "metrics": s.metrics}
                for s in self.sections
            ],
            "screenshots": self.screenshots,
            "recommendations": self.recommendations,
            "summary": {
                "pass": sum(1 for s in self.sections if s.status == "pass"),
                "fail": sum(1 for s in self.sections if s.status == "fail"),
                "warning": sum(1 for s in self.sections if s.status == "warning"),
                "total": len(self.sections),
            },
        }


class ReportBuilder:
    """Builder for creating detailed test reports."""

    def __init__(self, test_type: str, url: str):
        self.report = TestReport(
            test_type=test_type,
            url=url,
            start_time=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        )

    def add_section(
        self,
        title: str,
        status: str,
        findings: List[Dict] = None,
        metrics: Dict = None,
        details: str = "",
    ):
        """Add a section to the report."""
        self.report.sections.append(
            ReportSection(
                title=title,
                status=status,
                findings=findings or [],
                metrics=metrics or {},
                details=details,
            )
        )

    def add_screenshot(self, path: str):
        """Add a screenshot reference."""
        self.report.screenshots.append(path)

    def add_recommendation(self, recommendation: str):
        """Add a recommendation."""
        self.report.recommendations.append(recommendation)

    def set_status(self, status: str):
        """Set overall status."""
        self.report.overall_status = status

    def finalize(self):
        """Finalize the report with end time."""
        self.report.end_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"

        # Auto-determine overall status
        if any(s.status == "fail" for s in self.report.sections):
            self.report.overall_status = "fail"
        elif any(s.status == "warning" for s in self.report.sections):
            self.report.overall_status = "warning"
        else:
            self.report.overall_status = "pass"

    def get_report(self) -> TestReport:
        """Get the completed report."""
        return self.report
