"""
Accessibility testing using axe-core via Playwright.
"""

import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path

import structlog

logger = structlog.get_logger()


class AccessibilityTester:
    """Tests accessibility using axe-core."""
    
    def __init__(self):
        self.findings: List[Dict[str, Any]] = []
        self.axe_script: Optional[str] = None
    
    async def _load_axe(self, page) -> bool:
        """Load axe-core into page."""
        if self.axe_script is None:
            # Try to load from node_modules or CDN
            try:
                # Check if axe is installed locally
                axe_path = Path("node_modules/axe-core/axe.min.js")
                if axe_path.exists():
                    self.axe_script = axe_path.read_text()
                else:
                    # Load from CDN
                    import urllib.request
                    with urllib.request.urlopen(
                        "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.0/axe.min.js",
                        timeout=10
                    ) as response:
                        self.axe_script = response.read().decode('utf-8')
            except Exception as e:
                logger.error("axe_load_error", error=str(e))
                return False
        
        if self.axe_script and page:
            await page.evaluate(self.axe_script)
            return True
        
        return False
    
    async def test_accessibility(
        self,
        browser,
        url: str,
        rules: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Test accessibility using axe-core.
        
        Args:
            browser: BrowserAutomation instance
            url: URL to test
            rules: Optional list of specific rules to test
            
        Returns:
            Accessibility test results
        """
        self.findings = []
        start_time = datetime.now(timezone.utc)
        
        try:
            # Navigate to page
            result = await browser.visit(url)
            if not result["success"]:
                self.findings.append({
                    "title": "Navigation Failed",
                    "description": f"Cannot load page: {result.get('error')}",
                    "severity": "critical"
                })
                return self._build_result("fail", start_time)
            
            # Load axe-core
            if not browser.page:
                self.findings.append({
                    "title": "No Page Available",
                    "description": "Browser page not initialized",
                    "severity": "critical"
                })
                return self._build_result("fail", start_time)
            
            axe_loaded = await self._load_axe(browser.page)
            
            if not axe_loaded:
                # Fallback: manual accessibility checks
                logger.warning("axe_not_available", message="Using manual accessibility checks")
                return await self._manual_accessibility_check(browser, start_time)
            
            # Run axe
            options = {}
            if rules:
                options["runOnly"] = {
                    "type": "rule",
                    "values": rules
                }
            
            axe_result = await browser.page.evaluate(f"""
                () => {{
                    return new Promise((resolve) => {{
                        axe.run(document, {json.dumps(options)}, (err, results) => {{
                            resolve({{error: err ? err.message : null, results: results}});
                        }});
                    }});
                }}
            """)
            
            if axe_result.get("error"):
                self.findings.append({
                    "title": "Axe Error",
                    "description": axe_result["error"],
                    "severity": "critical"
                })
                return self._build_result("fail", start_time)
            
            results = axe_result.get("results", {})
            
            # Process violations
            violations = results.get("violations", [])
            passes = results.get("passes", [])
            incomplete = results.get("incomplete", [])
            
            for violation in violations:
                severity = self._map_axe_impact(violation.get("impact", "minor"))
                
                self.findings.append({
                    "title": violation.get("description", "Accessibility Violation"),
                    "description": f"{violation.get('help', '')} - {len(violation.get('nodes', []))} element(s) affected",
                    "severity": severity,
                    "rule_id": violation.get("id"),
                    "help_url": violation.get("helpUrl"),
                    "affected_elements": len(violation.get("nodes", []))
                })
            
            # Process incomplete (manual review needed)
            for item in incomplete:
                self.findings.append({
                    "title": f"Manual Review: {item.get('description', '')}",
                    "description": item.get("help", ""),
                    "severity": "info",
                    "rule_id": item.get("id"),
                    "help_url": item.get("helpUrl")
                })
            
            # Determine status
            critical_count = sum(1 for f in self.findings if f["severity"] == "critical")
            high_count = sum(1 for f in self.findings if f["severity"] == "high")
            
            if critical_count > 0:
                status = "fail"
            elif high_count > 0:
                status = "warning"
            else:
                status = "pass"
            
            return {
                **self._build_result(status, start_time),
                "summary": {
                    "violations": len(violations),
                    "passes": len(passes),
                    "incomplete": len(incomplete),
                    "critical": critical_count,
                    "high": high_count
                }
            }
            
        except Exception as e:
            logger.error("accessibility_test_error", error=str(e))
            self.findings.append({
                "title": "Test Error",
                "description": str(e),
                "severity": "critical"
            })
            return self._build_result("fail", start_time)
    
    async def _manual_accessibility_check(self, browser, start_time: datetime) -> Dict[str, Any]:
        """Fallback manual accessibility checks when axe is unavailable."""
        try:
            page = browser.page
            
            # Check images for alt text
            images = await page.query_selector_all("img")
            images_without_alt = 0
            for img in images:
                alt = await img.get_attribute("alt")
                if alt is None:
                    images_without_alt += 1
            
            if images_without_alt > 0:
                self.findings.append({
                    "title": "Images Without Alt Text",
                    "description": f"{images_without_alt} image(s) missing alt text",
                    "severity": "high"
                })
            
            # Check form labels
            inputs = await page.query_selector_all("input, select, textarea")
            inputs_without_labels = 0
            for inp in inputs:
                # Check for associated label
                id_attr = await inp.get_attribute("id")
                aria_label = await inp.get_attribute("aria-label")
                aria_labelled_by = await inp.get_attribute("aria-labelledby")
                placeholder = await inp.get_attribute("placeholder")
                
                if not any([aria_label, aria_labelled_by, placeholder]):
                    if id_attr:
                        # Check for label with for attribute
                        label = await page.query_selector(f"label[for='{id_attr}']")
                        if not label:
                            inputs_without_labels += 1
                    else:
                        inputs_without_labels += 1
            
            if inputs_without_labels > 0:
                self.findings.append({
                    "title": "Form Inputs Without Labels",
                    "description": f"{inputs_without_labels} input(s) missing labels",
                    "severity": "high"
                })
            
            # Check heading structure
            h1_count = len(await page.query_selector_all("h1"))
            if h1_count == 0:
                self.findings.append({
                    "title": "Missing H1",
                    "description": "Page has no h1 heading",
                    "severity": "medium"
                })
            elif h1_count > 1:
                self.findings.append({
                    "title": "Multiple H1s",
                    "description": f"Page has {h1_count} h1 headings (should be 1)",
                    "severity": "low"
                })
            
            # Check for lang attribute
            html_lang = await page.evaluate("() => document.documentElement.lang")
            if not html_lang:
                self.findings.append({
                    "title": "Missing Lang Attribute",
                    "description": "HTML element missing lang attribute",
                    "severity": "medium"
                })
            
            # Check for skip link
            skip_link = await page.query_selector("a[href^='#']")
            if not skip_link:
                self.findings.append({
                    "title": "No Skip Link",
                    "description": "No skip navigation link found",
                    "severity": "low"
                })
            
            status = "fail" if any(f["severity"] == "critical" for f in self.findings) else \
                     "warning" if any(f["severity"] == "high" for f in self.findings) else "pass"
            
            return self._build_result(status, start_time)
            
        except Exception as e:
            self.findings.append({
                "title": "Manual Check Error",
                "description": str(e),
                "severity": "critical"
            })
            return self._build_result("fail", start_time)
    
    def _map_axe_impact(self, impact: str) -> str:
        """Map axe-core impact to our severity levels."""
        mapping = {
            "critical": "critical",
            "serious": "high",
            "moderate": "medium",
            "minor": "low"
        }
        return mapping.get(impact, "medium")
    
    def _build_result(self, status: str, start_time: datetime) -> Dict[str, Any]:
        """Build test result."""
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        return {
            "status": status,
            "findings": self.findings,
            "duration_seconds": elapsed,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        }
