"""
Performance testing using Playwright metrics and Lighthouse CI.
"""

import os
import json
import subprocess
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path

import structlog

logger = structlog.get_logger()


class PerformanceTester:
    """Tests web performance using Playwright and Lighthouse."""

    def __init__(self):
        self.findings: List[Dict[str, Any]] = []
        self.metrics: Dict[str, Any] = {}

    async def test_performance(
        self, browser, url: str, thresholds: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Test performance using Playwright metrics.

        Args:
            browser: BrowserAutomation instance
            url: URL to test
            thresholds: Optional custom thresholds (lcp_ms, cls, ttfb_ms)

        Returns:
            Performance test results
        """
        self.findings = []
        self.metrics = {}
        start_time = datetime.now(timezone.utc)

        # Default thresholds (based on Core Web Vitals)
        default_thresholds = {
            "lcp_ms": 2500,  # Largest Contentful Paint
            "fid_ms": 100,  # First Input Delay (simulated via TBT)
            "cls": 0.1,  # Cumulative Layout Shift
            "ttfb_ms": 600,  # Time to First Byte
            "fcp_ms": 1800,  # First Contentful Paint
            "tbt_ms": 200,  # Total Blocking Time
        }

        if thresholds:
            default_thresholds.update(thresholds)

        try:
            # Enable performance metrics in Playwright
            if browser.page:
                # Inject performance observer
                await browser.page.evaluate("""
                    () => {
                        window.__performance_metrics = {};
                        new PerformanceObserver((list) => {
                            for (const entry of list.getEntries()) {
                                if (entry.entryType === 'largest-contentful-paint') {
                                    window.__performance_metrics.lcp = entry.startTime;
                                }
                                if (entry.entryType === 'layout-shift' && !entry.hadRecentInput) {
                                    window.__performance_metrics.cls = 
                                        (window.__performance_metrics.cls || 0) + entry.value;
                                }
                            }
                        }).observe({entryTypes: ['largest-contentful-paint', 'layout-shift']});
                    }
                """)

            # Navigate and measure
            nav_start = datetime.now(timezone.utc)
            result = await browser.visit(url, wait_until="networkidle")
            nav_end = datetime.now(timezone.utc)

            if not result["success"]:
                self.findings.append(
                    {
                        "title": "Navigation Failed",
                        "description": f"Cannot load page: {result.get('error')}",
                        "severity": "critical",
                    }
                )
                return self._build_result("fail", start_time)

            # Calculate basic timing
            self.metrics["navigation_time_ms"] = (nav_end - nav_start).total_seconds() * 1000
            self.metrics["http_status"] = result.get("status")

            # Get performance timing from browser
            if browser.page:
                timing_json = await browser.page.evaluate("""
                    () => JSON.stringify({
                        timing: performance.timing,
                        metrics: window.__performance_metrics || {},
                        paint: performance.getEntriesByType('paint').map(p => ({
                            name: p.name,
                            startTime: p.startTime
                        }))
                    })
                """)

                perf_data = json.loads(timing_json)
                timing = perf_data.get("timing", {})
                metrics = perf_data.get("metrics", {})
                paint = perf_data.get("paint", [])

                # Calculate TTFB
                if timing.get("responseStart") and timing.get("requestStart"):
                    ttfb = timing["responseStart"] - timing["requestStart"]
                    self.metrics["ttfb_ms"] = ttfb

                    if ttfb > default_thresholds["ttfb_ms"]:
                        self.findings.append(
                            {
                                "title": "Slow TTFB",
                                "description": f"Time to First Byte: {ttfb:.0f}ms (threshold: {default_thresholds['ttfb_ms']}ms)",
                                "severity": "high" if ttfb > 1000 else "medium",
                            }
                        )

                # Calculate FCP
                fcp_entry = next(
                    (p for p in paint if p.get("name") == "first-contentful-paint"), None
                )
                if fcp_entry:
                    fcp = fcp_entry["startTime"]
                    self.metrics["fcp_ms"] = fcp

                    if fcp > default_thresholds["fcp_ms"]:
                        self.findings.append(
                            {
                                "title": "Slow First Contentful Paint",
                                "description": f"FCP: {fcp:.0f}ms (threshold: {default_thresholds['fcp_ms']}ms)",
                                "severity": "high" if fcp > 3000 else "medium",
                            }
                        )

                # Get LCP
                if "lcp" in metrics:
                    lcp = metrics["lcp"]
                    self.metrics["lcp_ms"] = lcp

                    if lcp > default_thresholds["lcp_ms"]:
                        self.findings.append(
                            {
                                "title": "Slow Largest Contentful Paint",
                                "description": f"LCP: {lcp:.0f}ms (threshold: {default_thresholds['lcp_ms']}ms)",
                                "severity": "high" if lcp > 4000 else "medium",
                            }
                        )

                # Get CLS
                if "cls" in metrics:
                    cls = metrics["cls"]
                    self.metrics["cls"] = cls

                    if cls > default_thresholds["cls"]:
                        self.findings.append(
                            {
                                "title": "High Layout Shift",
                                "description": f"CLS: {cls:.3f} (threshold: {default_thresholds['cls']})",
                                "severity": "medium",
                            }
                        )

                # Calculate total page size
                resources = await browser.page.evaluate("""
                    () => performance.getEntriesByType('resource').reduce((acc, r) => {
                        acc.transferSize += r.transferSize || 0;
                        acc.count += 1;
                        return acc;
                    }, {transferSize: 0, count: 0})
                """)

                if resources:
                    self.metrics["total_transfer_size_bytes"] = resources.get("transferSize", 0)
                    self.metrics["resource_count"] = resources.get("count", 0)

                    size_mb = resources.get("transferSize", 0) / (1024 * 1024)
                    if size_mb > 5:
                        self.findings.append(
                            {
                                "title": "Large Page Size",
                                "description": f"Total transfer size: {size_mb:.1f}MB ({resources['count']} resources)",
                                "severity": "medium",
                            }
                        )

            # Run Lighthouse if available
            lighthouse_result = await self._run_lighthouse(url)
            if lighthouse_result:
                self.metrics["lighthouse"] = lighthouse_result

            # Determine overall status
            critical_count = sum(1 for f in self.findings if f["severity"] == "critical")
            high_count = sum(1 for f in self.findings if f["severity"] == "high")

            if critical_count > 0:
                status = "fail"
            elif high_count > 0:
                status = "warning"
            else:
                status = "pass"

            return self._build_result(status, start_time)

        except Exception as e:
            logger.error("performance_test_error", error=str(e))
            self.findings.append(
                {"title": "Test Error", "description": str(e), "severity": "critical"}
            )
            return self._build_result("fail", start_time)

    async def _run_lighthouse(self, url: str) -> Optional[Dict[str, Any]]:
        """Run Lighthouse CI if available."""
        try:
            # Check if lighthouse is installed
            result = subprocess.run(
                ["which", "lighthouse"], capture_output=True, text=True, timeout=5
            )

            if result.returncode != 0:
                logger.debug("lighthouse_not_installed")
                return None

            # Run lighthouse
            output_file = (
                f"/tmp/lighthouse_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
            )

            process = subprocess.run(
                [
                    "lighthouse",
                    url,
                    "--output=json",
                    f"--output-path={output_file}",
                    "--chrome-flags=--headless --no-sandbox",
                    "--only-categories=performance,accessibility,best-practices,seo",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if process.returncode != 0:
                logger.warning("lighthouse_error", stderr=process.stderr[:200])
                return None

            # Parse results
            with open(output_file, "r") as f:
                lighthouse_data = json.load(f)

            # Extract scores
            categories = lighthouse_data.get("categories", {})
            scores = {
                "performance": categories.get("performance", {}).get("score", 0) * 100,
                "accessibility": categories.get("accessibility", {}).get("score", 0) * 100,
                "best_practices": categories.get("best-practices", {}).get("score", 0) * 100,
                "seo": categories.get("seo", {}).get("score", 0) * 100,
            }

            # Add findings for low scores
            for category, score in scores.items():
                if score < 50:
                    self.findings.append(
                        {
                            "title": f"Low Lighthouse {category.title()} Score",
                            "description": f"Score: {score:.0f}/100",
                            "severity": "high",
                        }
                    )
                elif score < 90:
                    self.findings.append(
                        {
                            "title": f"Average Lighthouse {category.title()} Score",
                            "description": f"Score: {score:.0f}/100",
                            "severity": "medium",
                        }
                    )

            # Extract key metrics
            audits = lighthouse_data.get("audits", {})
            key_metrics = {
                "first_contentful_paint": audits.get("first-contentful-paint", {}).get(
                    "numericValue"
                ),
                "largest_contentful_paint": audits.get("largest-contentful-paint", {}).get(
                    "numericValue"
                ),
                "speed_index": audits.get("speed-index", {}).get("numericValue"),
                "total_blocking_time": audits.get("total-blocking-time", {}).get("numericValue"),
                "cumulative_layout_shift": audits.get("cumulative-layout-shift", {}).get(
                    "numericValue"
                ),
            }

            return {
                "scores": scores,
                "metrics": {k: v for k, v in key_metrics.items() if v is not None},
            }

        except subprocess.TimeoutExpired:
            logger.warning("lighthouse_timeout")
            return None
        except Exception as e:
            logger.warning("lighthouse_error", error=str(e))
            return None

    def _build_result(self, status: str, start_time: datetime) -> Dict[str, Any]:
        """Build test result."""
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        return {
            "status": status,
            "findings": self.findings,
            "metrics": self.metrics,
            "duration_seconds": elapsed,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        }
