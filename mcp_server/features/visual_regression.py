"""
Visual regression testing for Vectra QA.

Screenshot comparison with baseline management.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()

# Optional: Use PIL for image comparison if available
try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logger.warning("pillow_not_installed", message="Visual regression will use basic comparison")


class VisualRegressionTester:
    """Tests visual regression using screenshot comparison."""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.baselines_dir = vault_path / "Baselines"
        self.baselines_dir.mkdir(parents=True, exist_ok=True)
        self.findings: List[Dict[str, Any]] = []

    async def capture_baseline(
        self,
        browser,
        url: str,
        name: str,
        viewport: Optional[Tuple[int, int]] = None,
        full_page: bool = True,
    ) -> Dict[str, Any]:
        """
        Capture baseline screenshot.

        Args:
            browser: BrowserAutomation instance
            url: URL to capture
            name: Baseline name (e.g., "homepage-desktop")
            viewport: Optional (width, height) tuple
            full_page: Whether to capture full page

        Returns:
            Path to baseline screenshot
        """
        try:
            # Navigate to URL
            result = await browser.visit(url)
            if not result["success"]:
                return {"success": False, "error": f"Cannot navigate to {url}"}

            # Set viewport if specified
            if viewport and browser.page:
                await browser.page.set_viewport_size({"width": viewport[0], "height": viewport[1]})

            # Take screenshot
            baseline_path = self.baselines_dir / f"{name}.png"
            result = await browser.screenshot(str(baseline_path), full_page=full_page)

            if result["success"]:
                logger.info("baseline_captured", name=name, path=str(baseline_path))
                return {"success": True, "baseline_path": str(baseline_path), "name": name}
            else:
                return {"success": False, "error": result.get("error", "Screenshot failed")}

        except Exception as e:
            logger.error("baseline_capture_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def compare_screenshot(
        self,
        browser,
        url: str,
        name: str,
        threshold: float = 0.1,
        viewport: Optional[Tuple[int, int]] = None,
        full_page: bool = True,
    ) -> Dict[str, Any]:
        """
        Compare current screenshot against baseline.

        Args:
            browser: BrowserAutomation instance
            url: URL to capture
            name: Baseline name
            threshold: Pixel difference threshold (0.0-1.0)
            viewport: Optional viewport size
            full_page: Whether to capture full page

        Returns:
            Comparison results
        """
        self.findings = []
        start_time = datetime.now(timezone.utc)

        try:
            baseline_path = self.baselines_dir / f"{name}.png"

            if not baseline_path.exists():
                # No baseline exists, create one
                logger.info("no_baseline_exists", name=name)
                return await self.capture_baseline(browser, url, name, viewport, full_page)

            # Navigate and capture current
            result = await browser.visit(url)
            if not result["success"]:
                self.findings.append(
                    {
                        "title": "Navigation Failed",
                        "description": f"Cannot navigate to {url}",
                        "severity": "critical",
                    }
                )
                return self._build_result("fail", start_time)

            if viewport and browser.page:
                await browser.page.set_viewport_size({"width": viewport[0], "height": viewport[1]})

            # Take current screenshot
            current_path = self.baselines_dir / f"{name}_current.png"
            result = await browser.screenshot(str(current_path), full_page=full_page)

            if not result["success"]:
                self.findings.append(
                    {
                        "title": "Screenshot Failed",
                        "description": result.get("error", "Unknown error"),
                        "severity": "critical",
                    }
                )
                return self._build_result("fail", start_time)

            # Compare images
            if HAS_PIL:
                diff_result = await self._compare_images(str(baseline_path), str(current_path))
            else:
                # Fallback: file size comparison
                baseline_size = baseline_path.stat().st_size
                current_size = current_path.stat().st_size
                size_diff = abs(baseline_size - current_size) / max(baseline_size, 1)

                diff_result = {
                    "diff_percent": size_diff * 100,
                    "pixel_diff_count": -1,  # Unknown without PIL
                    "total_pixels": -1,
                }

                if size_diff > threshold:
                    self.findings.append(
                        {
                            "title": "Visual Difference Detected",
                            "description": f"File size changed by {size_diff*100:.1f}% (threshold: {threshold*100:.1f}%)",
                            "severity": "high" if size_diff > 0.5 else "medium",
                        }
                    )

            # Determine result
            if diff_result["diff_percent"] <= threshold * 100:
                status = "pass"
                self.findings.append(
                    {
                        "title": "Visual Match",
                        "description": f"Difference: {diff_result['diff_percent']:.2f}% (threshold: {threshold*100:.1f}%)",
                        "severity": "info",
                    }
                )
            else:
                status = "fail"
                self.findings.append(
                    {
                        "title": "Visual Mismatch",
                        "description": f"Difference: {diff_result['diff_percent']:.2f}% exceeds threshold {threshold*100:.1f}%",
                        "severity": "high",
                    }
                )

            return {
                **self._build_result(status, start_time),
                "baseline_path": str(baseline_path),
                "current_path": str(current_path),
                "diff_percent": diff_result["diff_percent"],
                "threshold_percent": threshold * 100,
            }

        except Exception as e:
            logger.error("visual_comparison_error", error=str(e))
            self.findings.append(
                {"title": "Comparison Error", "description": str(e), "severity": "critical"}
            )
            return self._build_result("fail", start_time)

    async def _compare_images(self, baseline_path: str, current_path: str) -> Dict[str, Any]:
        """Compare two images using PIL."""
        try:
            baseline = Image.open(baseline_path)
            current = Image.open(current_path)

            # Ensure same size
            if baseline.size != current.size:
                # Resize current to match baseline
                current = current.resize(baseline.size, Image.Resampling.LANCZOS)
                self.findings.append(
                    {
                        "title": "Size Mismatch",
                        "description": f"Baseline: {baseline.size}, Current: {Image.open(current_path).size}",
                        "severity": "warning",
                    }
                )

            # Convert to same mode
            if baseline.mode != current.mode:
                current = current.convert(baseline.mode)

            # Calculate difference
            diff_pixels = 0
            total_pixels = baseline.size[0] * baseline.size[1]

            # Use difference method
            diff_image = Image.new("RGBA", baseline.size)

            baseline_pixels = baseline.load()
            current_pixels = current.load()
            diff_pixels_data = diff_image.load()

            threshold = 10  # Pixel value difference threshold

            for y in range(baseline.size[1]):
                for x in range(baseline.size[0]):
                    baseline_pixel = baseline_pixels[x, y]
                    current_pixel = current_pixels[x, y]

                    # Handle different modes
                    if isinstance(baseline_pixel, int):
                        baseline_pixel = (baseline_pixel,)
                    if isinstance(current_pixel, int):
                        current_pixel = (current_pixel,)

                    # Compare first 3 channels (RGB)
                    pixel_diff = sum(
                        abs(baseline_pixel[i] - current_pixel[i])
                        for i in range(min(3, len(baseline_pixel)))
                    )

                    if pixel_diff > threshold:
                        diff_pixels += 1
                        diff_pixels_data[x, y] = (255, 0, 0, 255)  # Red for differences
                    else:
                        diff_pixels_data[x, y] = (0, 0, 0, 0)  # Transparent for matches

            diff_percent = (diff_pixels / total_pixels) * 100

            # Save diff image if there are differences
            if diff_pixels > 0:
                diff_path = self.baselines_dir / f"{Path(baseline_path).stem}_diff.png"
                diff_image.save(str(diff_path))
                logger.info("diff_image_saved", path=str(diff_path), diff_pixels=diff_pixels)

            return {
                "diff_percent": diff_percent,
                "pixel_diff_count": diff_pixels,
                "total_pixels": total_pixels,
            }

        except Exception as e:
            logger.error("image_comparison_error", error=str(e))
            return {
                "diff_percent": 100.0,
                "pixel_diff_count": -1,
                "total_pixels": -1,
                "error": str(e),
            }

    async def test_visual_regression(self, browser, url: str) -> Dict[str, Any]:
        """Test visual regression for a URL (wrapper for compare_screenshot)."""
        return await self.compare_screenshot(browser, url, name="default")

    def _build_result(self, status: str, start_time: datetime) -> Dict[str, Any]:
        """Build test result."""
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        return {
            "status": status,
            "findings": self.findings,
            "duration_seconds": elapsed,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        }
