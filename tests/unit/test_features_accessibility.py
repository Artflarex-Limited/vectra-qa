"""
Unit tests for mcp_server/features/accessibility.py.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from mcp_server.features.accessibility import AccessibilityTester


@pytest.mark.unit
class TestAccessibilityTester:
    """Tests for AccessibilityTester."""

    @pytest.fixture
    def tester(self):
        return AccessibilityTester()

    @pytest.fixture
    def mock_browser(self):
        browser = Mock()
        browser.page = AsyncMock()
        browser.visit = AsyncMock(return_value={"success": True})
        return browser

    def test_init(self):
        """Should initialize with empty findings."""
        tester = AccessibilityTester()
        assert tester.findings == []
        assert tester.axe_script is None

    @pytest.mark.asyncio
    async def test_load_axe_from_node_modules(self, tester):
        """Should load axe-core from node_modules."""
        mock_path = Mock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "axe.min.js content"

        with patch("mcp_server.features.accessibility.Path", return_value=mock_path):
            with patch.object(
                Path, "exists", return_value=True
            ):
                with patch.object(
                    Path, "read_text", return_value="axe.min.js content"
                ):
                    page = AsyncMock()
                    result = await tester._load_axe(page)

        assert result is True
        assert tester.axe_script == "axe.min.js content"
        page.evaluate.assert_awaited_once_with("axe.min.js content")

    @pytest.mark.asyncio
    async def test_load_axe_from_cdn(self, tester):
        """Should load axe-core from CDN when node_modules unavailable."""
        page = AsyncMock()

        with patch.object(Path, "exists", return_value=False):
            with patch(
                "urllib.request.urlopen"
            ) as mock_urlopen:
                mock_response = Mock()
                mock_response.read.return_value = b"cdn axe content"
                mock_urlopen.return_value.__enter__ = Mock(
                    return_value=mock_response
                )
                mock_urlopen.return_value.__exit__ = Mock(return_value=False)

                result = await tester._load_axe(page)

        assert result is True
        assert tester.axe_script == "cdn axe content"
        page.evaluate.assert_awaited_once_with("cdn axe content")

    @pytest.mark.asyncio
    async def test_load_axe_failure(self, tester):
        """Should return False when axe cannot be loaded."""
        page = AsyncMock()

        with patch.object(Path, "exists", return_value=False):
            with patch(
                "urllib.request.urlopen", side_effect=Exception("Network error")
            ):
                result = await tester._load_axe(page)

        assert result is False

    @pytest.mark.asyncio
    async def test_load_axe_already_loaded(self, tester):
        """Should reuse cached axe script."""
        tester.axe_script = "cached script"
        page = AsyncMock()

        result = await tester._load_axe(page)

        assert result is True
        page.evaluate.assert_awaited_once_with("cached script")

    @pytest.mark.asyncio
    async def test_load_axe_no_page(self, tester):
        """Should return False when page is None."""
        result = await tester._load_axe(None)
        assert result is False

    @pytest.mark.asyncio
    async def test_test_accessibility_navigation_failure(self, tester, mock_browser):
        """Should fail when navigation fails."""
        mock_browser.visit = AsyncMock(return_value={"success": False, "error": "Timeout"})

        result = await tester.test_accessibility(mock_browser, "https://example.com")

        assert result["status"] == "fail"
        assert any("Navigation Failed" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_test_accessibility_no_page(self, tester, mock_browser):
        """Should fail when browser page is not initialized."""
        mock_browser.page = None

        result = await tester.test_accessibility(mock_browser, "https://example.com")

        assert result["status"] == "fail"
        assert any("No Page Available" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_test_accessibility_with_violations(self, tester, mock_browser):
        """Should process axe-core violations correctly."""
        axe_results = {
            "error": None,
            "results": {
                "violations": [
                    {
                        "id": "color-contrast",
                        "description": "Elements must meet minimum color contrast ratio",
                        "help": "Ensure color contrast meets WCAG standards",
                        "impact": "serious",
                        "nodes": [{}, {}, {}],
                        "helpUrl": "https://deque.com/rules/color-contrast",
                    },
                    {
                        "id": "image-alt",
                        "description": "Images must have alt text",
                        "help": "Add alt text to images",
                        "impact": "critical",
                        "nodes": [{}],
                        "helpUrl": "https://deque.com/rules/image-alt",
                    },
                ],
                "passes": [{}, {}],
                "incomplete": [
                    {
                        "id": "aria-hidden",
                        "description": "ARIA hidden check",
                        "help": "Review ARIA usage",
                        "helpUrl": "https://deque.com/rules/aria-hidden",
                    }
                ],
            },
        }

        mock_browser.page.evaluate = AsyncMock(return_value=axe_results)
        tester.axe_script = "axe script"

        result = await tester.test_accessibility(mock_browser, "https://example.com")

        assert result["status"] == "fail"  # critical violation
        assert result["summary"]["violations"] == 2
        assert result["summary"]["passes"] == 2
        assert result["summary"]["incomplete"] == 1
        assert result["summary"]["critical"] == 1
        assert result["summary"]["high"] == 1

        violations = [f for f in result["findings"] if f.get("rule_id") == "color-contrast"]
        assert len(violations) == 1
        assert violations[0]["severity"] == "high"

        criticals = [f for f in result["findings"] if f.get("rule_id") == "image-alt"]
        assert len(criticals) == 1
        assert criticals[0]["severity"] == "critical"

        incomplete = [f for f in result["findings"] if "Manual Review" in f["title"]]
        assert len(incomplete) == 1

    @pytest.mark.asyncio
    async def test_test_accessibility_high_only(self, tester, mock_browser):
        """Should return warning for high severity without critical."""
        axe_results = {
            "error": None,
            "results": {
                "violations": [
                    {
                        "id": "link-name",
                        "description": "Links must have discernible text",
                        "help": "Provide link text",
                        "impact": "serious",
                        "nodes": [{}],
                        "helpUrl": "https://deque.com/rules/link-name",
                    }
                ],
                "passes": [],
                "incomplete": [],
            },
        }

        mock_browser.page.evaluate = AsyncMock(return_value=axe_results)
        tester.axe_script = "axe script"

        result = await tester.test_accessibility(mock_browser, "https://example.com")

        assert result["status"] == "warning"

    @pytest.mark.asyncio
    async def test_test_accessibility_pass(self, tester, mock_browser):
        """Should return pass when no violations found."""
        axe_results = {
            "error": None,
            "results": {
                "violations": [],
                "passes": [{}, {}, {}],
                "incomplete": [],
            },
        }

        mock_browser.page.evaluate = AsyncMock(return_value=axe_results)
        tester.axe_script = "axe script"

        result = await tester.test_accessibility(mock_browser, "https://example.com")

        assert result["status"] == "pass"
        assert result["summary"]["violations"] == 0

    @pytest.mark.asyncio
    async def test_test_accessibility_axe_error(self, tester, mock_browser):
        """Should handle axe-core runtime errors."""
        axe_results = {
            "error": "axe is not defined",
            "results": None,
        }

        mock_browser.page.evaluate = AsyncMock(return_value=axe_results)
        tester.axe_script = "axe script"

        result = await tester.test_accessibility(mock_browser, "https://example.com")

        assert result["status"] == "fail"
        assert any("Axe Error" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_test_accessibility_manual_fallback(self, tester, mock_browser):
        """Should fall back to manual checks when axe unavailable."""
        mock_browser.page.evaluate = AsyncMock(return_value="axe script")
        # First evaluate for axe injection, then for manual checks

        with patch.object(tester, "_load_axe", return_value=False):
            with patch.object(
                tester,
                "_manual_accessibility_check",
                return_value={"status": "pass", "findings": []},
            ) as mock_manual:
                await tester.test_accessibility(
                    mock_browser, "https://example.com"
                )

        mock_manual.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_test_accessibility_with_rules(self, tester, mock_browser):
        """Should pass specific rules to axe-core."""
        axe_results = {
            "error": None,
            "results": {"violations": [], "passes": [], "incomplete": []},
        }

        mock_browser.page.evaluate = AsyncMock(return_value=axe_results)
        tester.axe_script = "axe script"

        await tester.test_accessibility(
            mock_browser, "https://example.com", rules=["color-contrast", "image-alt"]
        )

        call_script = mock_browser.page.evaluate.call_args[0][0]
        assert "color-contrast" in call_script
        assert "image-alt" in call_script
        assert "runOnly" in call_script

    @pytest.mark.asyncio
    async def test_test_accessibility_exception(self, tester, mock_browser):
        """Should handle exceptions during accessibility test."""
        mock_browser.visit = AsyncMock(side_effect=Exception("Browser crashed"))

        result = await tester.test_accessibility(mock_browser, "https://example.com")

        assert result["status"] == "fail"
        assert any("Test Error" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_manual_accessibility_check_images(self, tester, mock_browser):
        """Should detect images without alt text."""
        mock_img_with_alt = AsyncMock()
        mock_img_with_alt.get_attribute.return_value = "Description"
        mock_img_no_alt = AsyncMock()
        mock_img_no_alt.get_attribute.return_value = None

        mock_browser.page.query_selector_all = AsyncMock(side_effect=[
            [mock_img_with_alt, mock_img_no_alt, mock_img_no_alt],  # images
            [],  # inputs
            [Mock()],  # h1
        ])
        mock_browser.page.query_selector = AsyncMock(return_value=None)
        mock_browser.page.evaluate = AsyncMock(return_value="en")

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert any(
            "Images Without Alt Text" in f["title"] for f in result["findings"]
        )
        assert any(
            "2 image(s) missing alt text" in f["description"]
            for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_manual_accessibility_check_inputs(self, tester, mock_browser):
        """Should detect inputs without labels."""
        mock_input_with_label = AsyncMock()
        mock_input_with_label.get_attribute.side_effect = ["username", None, None, None, None]
        mock_input_no_label = AsyncMock()
        mock_input_no_label.get_attribute.side_effect = [None, None, None, None, None]

        mock_browser.page.query_selector_all = AsyncMock(side_effect=[
            [],  # images
            [mock_input_with_label, mock_input_no_label],  # inputs
            [Mock()],  # h1
        ])
        mock_browser.page.query_selector = AsyncMock(return_value=Mock())
        mock_browser.page.evaluate = AsyncMock(return_value="en")

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert any(
            "Form Inputs Without Labels" in f["title"] for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_manual_accessibility_check_headings(self, tester, mock_browser):
        """Should detect missing or multiple h1 headings."""
        mock_browser.page.query_selector_all = AsyncMock(side_effect=[
            [],  # images
            [],  # inputs
            [],  # h1 - none
        ])
        mock_browser.page.query_selector = AsyncMock(return_value=None)
        mock_browser.page.evaluate = AsyncMock(return_value="en")

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert any("Missing H1" in f["title"] for f in result["findings"])
        assert any("medium" == f["severity"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_manual_accessibility_check_multiple_h1(self, tester, mock_browser):
        """Should detect multiple h1 headings."""
        mock_browser.page.query_selector_all = AsyncMock(side_effect=[
            [],  # images
            [],  # inputs
            [Mock(), Mock(), Mock()],  # h1 - 3
        ])
        mock_browser.page.query_selector = AsyncMock(return_value=None)
        mock_browser.page.evaluate = AsyncMock(return_value="en")

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert any("Multiple H1s" in f["title"] for f in result["findings"])
        assert any("low" == f["severity"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_manual_accessibility_check_lang(self, tester, mock_browser):
        """Should detect missing lang attribute."""
        mock_browser.page.query_selector_all = AsyncMock(side_effect=[
            [],  # images
            [],  # inputs
            [Mock()],  # h1
        ])
        mock_browser.page.query_selector = AsyncMock(return_value=None)
        mock_browser.page.evaluate = AsyncMock(return_value="")

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert any(
            "Missing Lang Attribute" in f["title"] for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_manual_accessibility_check_skip_link(self, tester, mock_browser):
        """Should detect missing skip link."""
        mock_browser.page.query_selector_all = AsyncMock(side_effect=[
            [],  # images
            [],  # inputs
            [Mock()],  # h1
        ])
        mock_browser.page.query_selector = AsyncMock(return_value=None)
        mock_browser.page.evaluate = AsyncMock(return_value="en")

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert any("No Skip Link" in f["title"] for f in result["findings"])
        assert any("low" == f["severity"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_manual_accessibility_check_skip_link_present(self, tester, mock_browser):
        """Should not flag skip link when present."""
        mock_browser.page.query_selector_all = AsyncMock(side_effect=[
            [],  # images
            [],  # inputs
            [Mock()],  # h1
        ])
        mock_browser.page.query_selector = AsyncMock(return_value=Mock())
        mock_browser.page.evaluate = AsyncMock(return_value="en")

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert not any("No Skip Link" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_manual_accessibility_check_status_fail(self, tester, mock_browser):
        """Should return fail status for critical findings."""
        mock_browser.page.query_selector_all = AsyncMock(side_effect=[
            [],  # images
            [],  # inputs
            [Mock()],  # h1
        ])
        mock_browser.page.query_selector = AsyncMock(return_value=None)
        mock_browser.page.evaluate = AsyncMock(return_value="en")

        # Inject a critical finding before calling
        tester.findings = [
            {"title": "Critical", "description": "Something", "severity": "critical"}
        ]

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert result["status"] == "fail"

    @pytest.mark.asyncio
    async def test_manual_accessibility_check_exception(self, tester, mock_browser):
        """Should handle exceptions during manual checks."""
        mock_browser.page.query_selector_all = AsyncMock(
            side_effect=Exception("DOM error")
        )

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert result["status"] == "fail"
        assert any("Manual Check Error" in f["title"] for f in result["findings"])

    def test_map_axe_impact(self, tester):
        """Should map axe-core impact levels correctly."""
        assert tester._map_axe_impact("critical") == "critical"
        assert tester._map_axe_impact("serious") == "high"
        assert tester._map_axe_impact("moderate") == "medium"
        assert tester._map_axe_impact("minor") == "low"
        assert tester._map_axe_impact("unknown") == "medium"
        assert tester._map_axe_impact("") == "medium"

    def test_build_result(self, tester):
        """Should build result with correct structure."""
        start = datetime.now(timezone.utc)
        result = tester._build_result("pass", start)

        assert result["status"] == "pass"
        assert result["findings"] == []
        assert "duration_seconds" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_manual_accessibility_input_with_id_no_label(self, tester, mock_browser):
        """Should flag inputs with id but no matching label."""
        mock_input = AsyncMock()
        mock_input.get_attribute.side_effect = ["email", None, None, None, None]

        mock_browser.page.query_selector_all = AsyncMock(side_effect=[
            [],  # images
            [mock_input],  # inputs
            [Mock()],  # h1
        ])
        mock_browser.page.query_selector = AsyncMock(return_value=None)
        mock_browser.page.evaluate = AsyncMock(return_value="en")

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert any(
            "Form Inputs Without Labels" in f["title"] for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_manual_accessibility_input_aria_label(self, tester, mock_browser):
        """Should not flag inputs with aria-label."""
        mock_input = AsyncMock()
        mock_input.get_attribute.side_effect = [None, "Search", None, None, None]

        mock_browser.page.query_selector_all = AsyncMock(side_effect=[
            [],  # images
            [mock_input],  # inputs
            [Mock()],  # h1
        ])
        mock_browser.page.query_selector = AsyncMock(return_value=None)
        mock_browser.page.evaluate = AsyncMock(return_value="en")

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert not any(
            "Form Inputs Without Labels" in f["title"] for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_manual_accessibility_input_placeholder(self, tester, mock_browser):
        """Should not flag inputs with placeholder."""
        mock_input = AsyncMock()
        mock_input.get_attribute.side_effect = [None, None, None, "Enter name", None]

        mock_browser.page.query_selector_all = AsyncMock(side_effect=[
            [],  # images
            [mock_input],  # inputs
            [Mock()],  # h1
        ])
        mock_browser.page.query_selector = AsyncMock(return_value=None)
        mock_browser.page.evaluate = AsyncMock(return_value="en")

        result = await tester._manual_accessibility_check(
            mock_browser, datetime.now(timezone.utc)
        )

        assert not any(
            "Form Inputs Without Labels" in f["title"] for f in result["findings"]
        )
