"""
Unit tests for mcp_server/features/visual_regression.py.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from mcp_server.features.visual_regression import VisualRegressionTester


class PixelMap:
    """Dict-like pixel data that supports both get and set item."""

    def __init__(self, data=None):
        self._data = data or {}

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value


@pytest.mark.unit
class TestVisualRegressionTester:
    """Tests for VisualRegressionTester."""

    @pytest.fixture
    def tester(self, tmp_path):
        return VisualRegressionTester(tmp_path)

    @pytest.fixture
    def mock_browser(self):
        browser = Mock()
        browser.page = AsyncMock()
        browser.visit = AsyncMock(return_value={"success": True})
        browser.screenshot = AsyncMock(return_value={"success": True})
        return browser

    def test_init(self, tmp_path):
        """Should initialize with baselines directory."""
        tester = VisualRegressionTester(tmp_path)
        assert tester.vault_path == tmp_path
        assert tester.baselines_dir.exists()
        assert tester.baselines_dir == tmp_path / "Baselines"
        assert tester.findings == []

    @pytest.mark.asyncio
    async def test_capture_baseline_success(self, tester, mock_browser):
        """Should capture baseline screenshot successfully."""
        result = await tester.capture_baseline(mock_browser, "https://example.com", "homepage")

        assert result["success"] is True
        assert result["name"] == "homepage"
        assert "baseline_path" in result
        assert "homepage.png" in result["baseline_path"]
        mock_browser.visit.assert_awaited_once_with("https://example.com")
        mock_browser.screenshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_capture_baseline_visit_failure(self, tester, mock_browser):
        """Should fail when navigation fails."""
        mock_browser.visit = AsyncMock(return_value={"success": False})

        result = await tester.capture_baseline(mock_browser, "https://example.com", "homepage")

        assert result["success"] is False
        assert "Cannot navigate" in result["error"]

    @pytest.mark.asyncio
    async def test_capture_baseline_screenshot_failure(self, tester, mock_browser):
        """Should fail when screenshot fails."""
        mock_browser.screenshot = AsyncMock(
            return_value={"success": False, "error": "Screenshot timeout"}
        )

        result = await tester.capture_baseline(mock_browser, "https://example.com", "homepage")

        assert result["success"] is False
        assert "Screenshot timeout" in result["error"]

    @pytest.mark.asyncio
    async def test_capture_baseline_with_viewport(self, tester, mock_browser):
        """Should set viewport before capturing."""
        await tester.capture_baseline(
            mock_browser,
            "https://example.com",
            "homepage",
            viewport=(1280, 720),
            full_page=False,
        )

        mock_browser.page.set_viewport_size.assert_awaited_once_with({"width": 1280, "height": 720})
        mock_browser.screenshot.assert_awaited_once()
        call_args = mock_browser.screenshot.call_args
        assert call_args.kwargs.get("full_page") is False

    @pytest.mark.asyncio
    async def test_capture_baseline_exception(self, tester, mock_browser):
        """Should handle exceptions during baseline capture."""
        mock_browser.visit = AsyncMock(side_effect=Exception("Network error"))

        result = await tester.capture_baseline(mock_browser, "https://example.com", "homepage")

        assert result["success"] is False
        assert "Network error" in result["error"]

    @pytest.mark.asyncio
    async def test_compare_screenshot_no_baseline(self, tester, mock_browser):
        """Should create baseline when none exists."""
        result = await tester.compare_screenshot(mock_browser, "https://example.com", "new_page")

        assert result["success"] is True
        assert result["name"] == "new_page"
        assert "baseline_path" in result

    @pytest.mark.asyncio
    async def test_compare_screenshot_navigation_failure(self, tester, mock_browser):
        """Should fail when navigation fails during comparison."""
        # Create baseline first
        baseline_path = tester.baselines_dir / "existing.png"
        baseline_path.write_bytes(b"fake_png_data")

        mock_browser.visit = AsyncMock(return_value={"success": False})

        result = await tester.compare_screenshot(mock_browser, "https://example.com", "existing")

        assert result["status"] == "fail"
        assert any("Navigation Failed" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_compare_screenshot_screenshot_failure(self, tester, mock_browser):
        """Should fail when screenshot fails during comparison."""
        baseline_path = tester.baselines_dir / "existing.png"
        baseline_path.write_bytes(b"fake_png_data")

        mock_browser.screenshot = AsyncMock(
            return_value={"success": False, "error": "Camera broken"}
        )

        result = await tester.compare_screenshot(mock_browser, "https://example.com", "existing")

        assert result["status"] == "fail"
        assert any("Screenshot Failed" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_compare_screenshot_with_pil_pass(self, tester, mock_browser):
        """Should pass when images match within threshold."""
        baseline_path = tester.baselines_dir / "match.png"
        baseline_path.write_bytes(b"fake_png_data")

        with patch.object(
            tester,
            "_compare_images",
            return_value={"diff_percent": 0.5, "pixel_diff_count": 10, "total_pixels": 1000},
        ):
            with patch("mcp_server.features.visual_regression.HAS_PIL", True):
                result = await tester.compare_screenshot(
                    mock_browser, "https://example.com", "match", threshold=0.1
                )

        assert result["status"] == "pass"
        assert result["diff_percent"] == 0.5
        assert any("Visual Match" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_compare_screenshot_with_pil_fail(self, tester, mock_browser):
        """Should fail when images exceed threshold."""
        baseline_path = tester.baselines_dir / "mismatch.png"
        baseline_path.write_bytes(b"fake_png_data")

        with patch.object(
            tester,
            "_compare_images",
            return_value={"diff_percent": 15.0, "pixel_diff_count": 150, "total_pixels": 1000},
        ):
            with patch("mcp_server.features.visual_regression.HAS_PIL", True):
                result = await tester.compare_screenshot(
                    mock_browser, "https://example.com", "mismatch", threshold=0.1
                )

        assert result["status"] == "fail"
        assert result["diff_percent"] == 15.0
        assert any("Visual Mismatch" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_compare_screenshot_no_pil_fallback(self, tester, mock_browser):
        """Should use file size comparison when PIL unavailable."""
        baseline_path = tester.baselines_dir / "no_pil.png"
        baseline_path.write_bytes(b"A" * 1000)

        async def side_effect(path, **kwargs):
            Path(path).write_bytes(b"B" * 500)
            return {"success": True}

        mock_browser.screenshot = AsyncMock(side_effect=side_effect)

        with patch("mcp_server.features.visual_regression.HAS_PIL", False):
            result = await tester.compare_screenshot(
                mock_browser, "https://example.com", "no_pil", threshold=0.2
            )

        assert result["status"] == "fail"
        assert any("Visual Difference" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_compare_screenshot_with_viewport(self, tester, mock_browser):
        """Should set viewport during comparison."""
        baseline_path = tester.baselines_dir / "viewport.png"
        baseline_path.write_bytes(b"fake_png_data")

        with patch.object(
            tester,
            "_compare_images",
            return_value={"diff_percent": 0.0, "pixel_diff_count": 0, "total_pixels": 1},
        ):
            with patch("mcp_server.features.visual_regression.HAS_PIL", True):
                result = await tester.compare_screenshot(
                    mock_browser, "https://example.com", "viewport", viewport=(1280, 720)
                )

        assert result["status"] == "pass"
        mock_browser.page.set_viewport_size.assert_awaited_once_with({"width": 1280, "height": 720})

    @pytest.mark.asyncio
    async def test_compare_screenshot_exception(self, tester, mock_browser):
        """Should handle exceptions during comparison."""
        baseline_path = tester.baselines_dir / "err.png"
        baseline_path.write_bytes(b"fake_png_data")

        mock_browser.visit = AsyncMock(side_effect=Exception("Kaboom"))

        result = await tester.compare_screenshot(mock_browser, "https://example.com", "err")

        assert result["status"] == "fail"
        assert any("Comparison Error" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_compare_images_with_pil(self, tester):
        """Should compare images using PIL."""
        pixel_data = {(x, y): (128, 128, 128) for x in range(10) for y in range(10)}

        mock_baseline = Mock()
        mock_baseline.size = (10, 10)
        mock_baseline.mode = "RGB"
        mock_baseline.load.return_value = PixelMap(pixel_data)

        mock_current = Mock()
        mock_current.size = (10, 10)
        mock_current.mode = "RGB"
        mock_current.load.return_value = PixelMap(pixel_data)

        mock_diff_image = Mock()
        mock_diff_image.load.return_value = PixelMap()

        mock_image = Mock()
        mock_image.open.side_effect = [mock_baseline, mock_current]
        mock_image.new.return_value = mock_diff_image
        mock_image.Resampling = Mock()
        mock_image.Resampling.LANCZOS = Mock()

        with patch("mcp_server.features.visual_regression.Image", mock_image, create=True):
            result = await tester._compare_images("baseline.png", "current.png")

        assert result["diff_percent"] == 0.0
        assert result["pixel_diff_count"] == 0
        assert result["total_pixels"] == 100

    @pytest.mark.asyncio
    async def test_compare_images_size_mismatch(self, tester):
        """Should resize images when sizes differ."""
        pixel_data = {(x, y): (128, 128, 128) for x in range(10) for y in range(10)}

        mock_baseline = Mock()
        mock_baseline.size = (10, 10)
        mock_baseline.mode = "RGB"
        mock_baseline.load.return_value = PixelMap(pixel_data)

        mock_resized = Mock()
        mock_resized.size = (10, 10)
        mock_resized.mode = "RGB"
        mock_resized.load.return_value = PixelMap(pixel_data)

        mock_current = Mock()
        mock_current.size = (20, 20)
        mock_current.mode = "RGB"
        mock_current.load.return_value = PixelMap(pixel_data)
        mock_current.resize.return_value = mock_resized

        mock_diff_image = Mock()
        mock_diff_image.load.return_value = PixelMap()

        mock_image = Mock()
        mock_image.open.side_effect = [mock_baseline, mock_current, mock_current]
        mock_image.new.return_value = mock_diff_image
        mock_image.Resampling = Mock()
        mock_image.Resampling.LANCZOS = Mock()

        with patch("mcp_server.features.visual_regression.Image", mock_image, create=True):
            result = await tester._compare_images("baseline.png", "current.png")

        mock_current.resize.assert_called_once()
        assert result["diff_percent"] == 0.0
        assert any("Size Mismatch" in f["title"] for f in tester.findings)

    @pytest.mark.asyncio
    async def test_compare_images_mode_mismatch(self, tester):
        """Should convert image modes when they differ."""
        pixel_data = {(x, y): (128, 128, 128) for x in range(2) for y in range(2)}

        mock_baseline = Mock()
        mock_baseline.size = (2, 2)
        mock_baseline.mode = "RGB"
        mock_baseline.load.return_value = PixelMap(pixel_data)

        mock_current = Mock()
        mock_current.size = (2, 2)
        mock_current.mode = "RGBA"
        mock_current.load.return_value = PixelMap(pixel_data)

        mock_diff_image = Mock()
        mock_diff_image.load.return_value = PixelMap()

        mock_image = Mock()
        mock_image.open.side_effect = [mock_baseline, mock_current]
        mock_image.new.return_value = mock_diff_image
        mock_image.Resampling = Mock()
        mock_image.Resampling.LANCZOS = Mock()

        with patch("mcp_server.features.visual_regression.Image", mock_image, create=True):
            await tester._compare_images("baseline.png", "current.png")

        mock_current.convert.assert_called_once_with("RGB")

    @pytest.mark.asyncio
    async def test_compare_images_int_pixels(self, tester):
        """Should handle integer pixel values (grayscale mode)."""
        baseline_pixels = {
            (0, 0): 128,
            (1, 0): 255,
        }
        current_pixels = {
            (0, 0): 128,
            (1, 0): 0,
        }

        mock_baseline = Mock()
        mock_baseline.size = (2, 1)
        mock_baseline.mode = "L"
        mock_baseline.load.return_value = PixelMap(baseline_pixels)

        mock_current = Mock()
        mock_current.size = (2, 1)
        mock_current.mode = "L"
        mock_current.load.return_value = PixelMap(current_pixels)

        mock_diff_image = Mock()
        mock_diff_image.load.return_value = PixelMap()

        mock_image = Mock()
        mock_image.open.side_effect = [mock_baseline, mock_current]
        mock_image.new.return_value = mock_diff_image
        mock_image.Resampling = Mock()
        mock_image.Resampling.LANCZOS = Mock()

        with patch("mcp_server.features.visual_regression.Image", mock_image, create=True):
            result = await tester._compare_images("baseline.png", "current.png")

        assert result["pixel_diff_count"] == 1
        assert result["diff_percent"] == 50.0

    @pytest.mark.asyncio
    async def test_compare_images_with_differences(self, tester):
        """Should detect pixel differences."""
        baseline_pixels = {
            (0, 0): (0, 0, 0),
            (1, 0): (255, 255, 255),
            (0, 1): (0, 0, 0),
            (1, 1): (255, 255, 255),
        }
        current_pixels = {
            (0, 0): (255, 255, 255),
            (1, 0): (255, 255, 255),
            (0, 1): (0, 0, 0),
            (1, 1): (0, 0, 0),
        }

        mock_baseline = Mock()
        mock_baseline.size = (2, 2)
        mock_baseline.mode = "RGB"
        mock_baseline.load.return_value = PixelMap(baseline_pixels)

        mock_current = Mock()
        mock_current.size = (2, 2)
        mock_current.mode = "RGB"
        mock_current.load.return_value = PixelMap(current_pixels)

        mock_diff_image = Mock()
        diff_map = PixelMap()
        mock_diff_image.load.return_value = diff_map

        mock_image = Mock()
        mock_image.open.side_effect = [mock_baseline, mock_current]
        mock_image.new.return_value = mock_diff_image
        mock_image.Resampling = Mock()
        mock_image.Resampling.LANCZOS = Mock()

        with patch("mcp_server.features.visual_regression.Image", mock_image, create=True):
            result = await tester._compare_images("baseline.png", "current.png")

        assert result["pixel_diff_count"] == 2
        assert result["diff_percent"] == 50.0
        mock_diff_image.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_compare_images_exception(self, tester):
        """Should handle image comparison errors."""
        with patch(
            "mcp_server.features.visual_regression.Image.open",
            side_effect=Exception("Corrupt image"),
            create=True,
        ):
            result = await tester._compare_images("baseline.png", "current.png")

        assert result["diff_percent"] == 100.0
        assert result["pixel_diff_count"] == -1
        assert "error" in result

    @pytest.mark.asyncio
    async def test_test_visual_regression(self, tester, mock_browser):
        """Should delegate to compare_screenshot."""
        baseline_path = tester.baselines_dir / "default.png"
        baseline_path.write_bytes(b"fake")

        with patch.object(
            tester, "compare_screenshot", return_value={"status": "pass"}
        ) as mock_compare:
            result = await tester.test_visual_regression(mock_browser, "https://example.com")

        mock_compare.assert_awaited_once_with(mock_browser, "https://example.com", name="default")
        assert result["status"] == "pass"

    def test_build_result(self, tester):
        """Should build result with correct structure."""
        start = datetime.now(timezone.utc)
        result = tester._build_result("pass", start)

        assert result["status"] == "pass"
        assert result["findings"] == []
        assert "duration_seconds" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_compare_screenshot_no_pil_small_diff(self, tester, mock_browser):
        """Should detect small file size differences with medium severity."""
        baseline_path = tester.baselines_dir / "small_diff.png"
        baseline_path.write_bytes(b"A" * 1000)

        async def side_effect(path, **kwargs):
            Path(path).write_bytes(b"A" * 900)  # 10% difference
            return {"success": True}

        mock_browser.screenshot = AsyncMock(side_effect=side_effect)

        with patch("mcp_server.features.visual_regression.HAS_PIL", False):
            result = await tester.compare_screenshot(
                mock_browser, "https://example.com", "small_diff", threshold=0.2
            )

        assert result["status"] == "pass"  # 10% < 20% threshold
        assert any("Visual Match" in f["title"] for f in result["findings"])
