"""
Unit tests for mcp_server/features/performance.py.
"""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch, mock_open

from mcp_server.features.performance import PerformanceTester


@pytest.mark.unit
class TestPerformanceTester:
    """Tests for PerformanceTester."""

    @pytest.fixture
    def tester(self):
        return PerformanceTester()

    @pytest.fixture
    def mock_browser(self):
        browser = Mock()
        browser.page = AsyncMock()
        browser.visit = AsyncMock(return_value={"success": True, "status": 200})
        return browser

    def test_init(self):
        """Should initialize with empty findings and metrics."""
        tester = PerformanceTester()
        assert tester.findings == []
        assert tester.metrics == {}

    @pytest.mark.asyncio
    async def test_test_performance_success(self, tester, mock_browser):
        """Should measure performance metrics successfully."""
        perf_json = json.dumps({
            "timing": {"responseStart": 101, "requestStart": 1},
            "metrics": {"lcp": 1200, "cls": 0.05},
            "paint": [{"name": "first-contentful-paint", "startTime": 800}],
        })
        resources = {"transferSize": 1024000, "count": 15}

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return resources
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser, "https://example.com"
            )

        assert result["status"] == "pass"
        assert result["metrics"]["ttfb_ms"] == 100
        assert result["metrics"]["fcp_ms"] == 800
        assert result["metrics"]["lcp_ms"] == 1200
        assert result["metrics"]["cls"] == 0.05
        assert result["metrics"]["total_transfer_size_bytes"] == 1024000
        assert result["metrics"]["resource_count"] == 15
        assert result["metrics"]["http_status"] == 200

    @pytest.mark.asyncio
    async def test_test_performance_navigation_failure(self, tester, mock_browser):
        """Should fail when navigation fails."""
        mock_browser.visit = AsyncMock(return_value={"success": False, "error": "Timeout"})

        result = await tester.test_performance(mock_browser, "https://example.com")

        assert result["status"] == "fail"
        assert any("Navigation Failed" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_test_performance_no_page(self, tester, mock_browser):
        """Should work when browser page is None."""
        mock_browser.page = None
        mock_browser.visit = AsyncMock(return_value={"success": True, "status": 200})

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser, "https://example.com"
            )

        assert result["status"] == "pass"

    @pytest.mark.asyncio
    async def test_test_performance_slow_ttfb(self, tester, mock_browser):
        """Should flag slow TTFB."""
        perf_json = json.dumps({
            "timing": {"responseStart": 1501, "requestStart": 1},
            "metrics": {},
            "paint": [],
        })

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return {"transferSize": 1000, "count": 1}
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser, "https://example.com"
            )

        assert any("Slow TTFB" in f["title"] for f in result["findings"])
        assert result["metrics"]["ttfb_ms"] == 1500

    @pytest.mark.asyncio
    async def test_test_performance_slow_ttfb_critical(self, tester, mock_browser):
        """Should flag critical TTFB over 1000ms."""
        perf_json = json.dumps({
            "timing": {"responseStart": 2001, "requestStart": 1},
            "metrics": {},
            "paint": [],
        })

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return {"transferSize": 1000, "count": 1}
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser, "https://example.com"
            )

        ttfb_finding = next(f for f in result["findings"] if "Slow TTFB" in f["title"])
        assert ttfb_finding["severity"] == "high"

    @pytest.mark.asyncio
    async def test_test_performance_slow_fcp(self, tester, mock_browser):
        """Should flag slow FCP."""
        perf_json = json.dumps({
            "timing": {"responseStart": 101, "requestStart": 1},
            "metrics": {},
            "paint": [{"name": "first-contentful-paint", "startTime": 2500}],
        })

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return {"transferSize": 1000, "count": 1}
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser, "https://example.com"
            )

        assert any("Slow First Contentful Paint" in f["title"] for f in result["findings"])
        assert result["metrics"]["fcp_ms"] == 2500

    @pytest.mark.asyncio
    async def test_test_performance_slow_fcp_critical(self, tester, mock_browser):
        """Should flag critical FCP over 3000ms."""
        perf_json = json.dumps({
            "timing": {"responseStart": 101, "requestStart": 1},
            "metrics": {},
            "paint": [{"name": "first-contentful-paint", "startTime": 3500}],
        })

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return {"transferSize": 1000, "count": 1}
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser, "https://example.com"
            )

        fcp_finding = next(
            f for f in result["findings"] if "Slow First Contentful Paint" in f["title"]
        )
        assert fcp_finding["severity"] == "high"

    @pytest.mark.asyncio
    async def test_test_performance_slow_lcp(self, tester, mock_browser):
        """Should flag slow LCP."""
        perf_json = json.dumps({
            "timing": {"responseStart": 101, "requestStart": 1},
            "metrics": {"lcp": 3000},
            "paint": [],
        })

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return {"transferSize": 1000, "count": 1}
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser, "https://example.com"
            )

        assert any("Slow Largest Contentful Paint" in f["title"] for f in result["findings"])
        assert result["metrics"]["lcp_ms"] == 3000

    @pytest.mark.asyncio
    async def test_test_performance_slow_lcp_critical(self, tester, mock_browser):
        """Should flag critical LCP over 4000ms."""
        perf_json = json.dumps({
            "timing": {"responseStart": 101, "requestStart": 1},
            "metrics": {"lcp": 4500},
            "paint": [],
        })

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return {"transferSize": 1000, "count": 1}
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser, "https://example.com"
            )

        lcp_finding = next(
            f for f in result["findings"] if "Slow Largest Contentful Paint" in f["title"]
        )
        assert lcp_finding["severity"] == "high"

    @pytest.mark.asyncio
    async def test_test_performance_high_cls(self, tester, mock_browser):
        """Should flag high CLS."""
        perf_json = json.dumps({
            "timing": {"responseStart": 101, "requestStart": 1},
            "metrics": {"cls": 0.25},
            "paint": [],
        })

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return {"transferSize": 1000, "count": 1}
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser, "https://example.com"
            )

        assert any("High Layout Shift" in f["title"] for f in result["findings"])
        assert result["metrics"]["cls"] == 0.25

    @pytest.mark.asyncio
    async def test_test_performance_large_page(self, tester, mock_browser):
        """Should flag large page size."""
        perf_json = json.dumps({
            "timing": {"responseStart": 101, "requestStart": 1},
            "metrics": {},
            "paint": [],
        })

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return {"transferSize": 10 * 1024 * 1024, "count": 50}  # 10MB
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser, "https://example.com"
            )

        assert any("Large Page Size" in f["title"] for f in result["findings"])
        assert result["metrics"]["total_transfer_size_bytes"] == 10 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_test_performance_custom_thresholds(self, tester, mock_browser):
        """Should use custom thresholds."""
        perf_json = json.dumps({
            "timing": {"responseStart": 301, "requestStart": 1},
            "metrics": {},
            "paint": [{"name": "first-contentful-paint", "startTime": 1200}],
        })

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return {"transferSize": 1000, "count": 1}
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser,
                "https://example.com",
                thresholds={"ttfb_ms": 200, "fcp_ms": 1000},
            )

        assert any("Slow TTFB" in f["title"] for f in result["findings"])
        assert any("Slow First Contentful Paint" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_test_performance_warning_status(self, tester, mock_browser):
        """Should return warning for high severity findings."""
        perf_json = json.dumps({
            "timing": {"responseStart": 1501, "requestStart": 1},  # slow TTFB = high
            "metrics": {},
            "paint": [],
        })

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return {"transferSize": 1000, "count": 1}
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        with patch.object(tester, "_run_lighthouse", return_value=None):
            result = await tester.test_performance(
                mock_browser, "https://example.com"
            )

        assert result["status"] == "warning"

    @pytest.mark.asyncio
    async def test_test_performance_fail_status(self, tester, mock_browser):
        """Should return fail for critical findings."""
        mock_browser.visit = AsyncMock(return_value={"success": False})

        result = await tester.test_performance(mock_browser, "https://example.com")
        assert result["status"] == "fail"

    @pytest.mark.asyncio
    async def test_test_performance_exception(self, tester, mock_browser):
        """Should handle exceptions during performance test."""
        mock_browser.visit = AsyncMock(side_effect=Exception("Browser crash"))

        result = await tester.test_performance(mock_browser, "https://example.com")

        assert result["status"] == "fail"
        assert any("Test Error" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_test_performance_with_lighthouse(self, tester, mock_browser, tmp_path):
        """Should include lighthouse results when available."""
        perf_json = json.dumps({
            "timing": {"responseStart": 101, "requestStart": 1},
            "metrics": {},
            "paint": [],
        })

        async def mock_evaluate(script):
            if "performance.getEntriesByType('resource')" in script:
                return {"transferSize": 1000, "count": 1}
            elif "performance.timing" in script:
                return perf_json
            return None

        mock_browser.page.evaluate = AsyncMock(side_effect=mock_evaluate)

        lighthouse_data = {
            "categories": {
                "performance": {"score": 0.85},
                "accessibility": {"score": 0.95},
                "best-practices": {"score": 0.90},
                "seo": {"score": 0.88},
            },
            "audits": {
                "first-contentful-paint": {"numericValue": 1200},
                "largest-contentful-paint": {"numericValue": 2500},
            },
        }

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="/usr/bin/lighthouse"),
                Mock(returncode=0, stdout="", stderr=""),
            ]

            with patch("builtins.open", MagicMock()) as mock_open:
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.read.return_value = json.dumps(lighthouse_data)
                mock_open.return_value = mock_file

                with patch("json.load", return_value=lighthouse_data):
                    result = await tester.test_performance(
                        mock_browser, "https://example.com"
                    )

        assert "lighthouse" in result["metrics"]

    @pytest.mark.asyncio
    async def test_run_lighthouse_not_installed(self, tester):
        """Should return None when lighthouse not installed."""
        with patch("subprocess.run", return_value=Mock(returncode=1)) as mock_run:
            result = await tester._run_lighthouse("https://example.com")

        assert result is None
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_lighthouse_error(self, tester):
        """Should return None when lighthouse run fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="/usr/bin/lighthouse"),
                Mock(returncode=1, stdout="", stderr="error"),
            ]

            result = await tester._run_lighthouse("https://example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_run_lighthouse_timeout(self, tester):
        """Should handle lighthouse timeout."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="/usr/bin/lighthouse"),
                subprocess.TimeoutExpired("lighthouse", 120),
            ]

            result = await tester._run_lighthouse("https://example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_run_lighthouse_exception(self, tester):
        """Should handle lighthouse exceptions."""
        with patch("subprocess.run", side_effect=Exception("Lighthouse crash")):
            result = await tester._run_lighthouse("https://example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_run_lighthouse_low_scores(self, tester):
        """Should add findings for low lighthouse scores."""
        lighthouse_data = {
            "categories": {
                "performance": {"score": 0.30},
                "accessibility": {"score": 0.95},
                "best-practices": {"score": 0.40},
                "seo": {"score": 0.85},
            },
            "audits": {},
        }

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="/usr/bin/lighthouse"),
                Mock(returncode=0, stdout="", stderr=""),
            ]

            m = mock_open(read_data=json.dumps(lighthouse_data))
            with patch("builtins.open", m):
                result = await tester._run_lighthouse("https://example.com")

        assert result is not None
        titles = [f["title"] for f in tester.findings]
        assert any("Low Lighthouse Performance Score" in t for t in titles)
        assert any("Low Lighthouse Best_Practices Score" in t for t in titles)

    def test_build_result(self, tester):
        """Should build result with correct structure."""
        start = datetime.now(timezone.utc)
        result = tester._build_result("pass", start)

        assert result["status"] == "pass"
        assert result["findings"] == []
        assert "metrics" in result
        assert "duration_seconds" in result
        assert "timestamp" in result
