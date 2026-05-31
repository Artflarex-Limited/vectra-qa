#!/usr/bin/env python3
"""
Feature Tester Worker

Executes Phase 4 specialized tests based on agent role:
- auth_tester: Authentication flow testing
- visual_regression_tester: Visual regression testing
- performance_tester: Performance testing
- api_contract_tester: API contract validation
- accessibility_tester: Accessibility testing
- multi_browser_tester: Cross-browser testing

Usage:
    python agents/feature_tester/worker.py <agent_id> <memory_node_path>
"""

import sys
import os
import asyncio
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp_server.tools import get_vault
from mcp_server.browser_tools import BrowserAutomation
from mcp_server.features.auth_testing import AuthFlowTester
from mcp_server.features.visual_regression import VisualRegressionTester
from mcp_server.features.performance import PerformanceTester
from mcp_server.features.api_contract import APIContractTester
from mcp_server.features.accessibility import AccessibilityTester
from mcp_server.features.multi_browser import MultiBrowserTester

logger = structlog.get_logger()

VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault"))


class FeatureTesterWorker:
    """Worker that executes specialized feature tests."""

    def __init__(self, agent_id: str, memory_node: str):
        self.agent_id = agent_id
        self.memory_node = memory_node
        self.role = os.getenv("AGENT_ROLE", "feature_tester")
        self.objective = os.getenv("AGENT_OBJECTIVE", "")
        self.vault = get_vault()
        self.start_time = datetime.now(timezone.utc)
        self.results: Dict[str, Any] = {}

    def _parse_url(self) -> Optional[str]:
        """Extract URL from objective."""
        # Look for URLs in the objective
        url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+'
        matches = re.findall(url_pattern, self.objective)
        if matches:
            return matches[0]
        return None

    def _parse_credentials(self) -> Dict[str, str]:
        """Extract credentials from objective if present."""
        creds = {}
        # Look for username: "value" or username: value patterns
        username_match = re.search(
            r'username[:\s]+["\']?([^"\'\s]+)["\']?', self.objective, re.IGNORECASE
        )
        password_match = re.search(
            r'password[:\s]+["\']?([^"\'\s]+)["\']?', self.objective, re.IGNORECASE
        )
        if username_match:
            creds["username"] = username_match.group(1)
        if password_match:
            creds["password"] = password_match.group(1)
        return creds

    def _parse_schema_path(self) -> Optional[str]:
        """Extract OpenAPI schema path from objective."""
        match = re.search(r'schema[:\s]+["\']?([^"\'\s]+)["\']?', self.objective, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    async def _run_auth_test(self, url: str) -> Dict[str, Any]:
        """Run authentication flow test."""
        logger.info("running_auth_test", url=url)
        browser = BrowserAutomation()
        await browser.start()

        try:
            tester = AuthFlowTester(browser)
            creds = self._parse_credentials()

            # Test login if credentials provided
            if creds.get("username") and creds.get("password"):
                login_url = f"{url.rstrip('/')}/login" if not url.endswith("/login") else url
                result = await tester.test_login_flow(
                    login_url=login_url, username=creds["username"], password=creds["password"]
                )
                self.results["login_test"] = result

            # Test logout
            logout_url = f"{url.rstrip('/')}/logout"
            result = await tester.test_logout_flow(logout_url=logout_url)
            self.results["logout_test"] = result

            return self.results

        finally:
            await browser.close()

    async def _run_visual_regression_test(self, url: str) -> Dict[str, Any]:
        """Run visual regression test."""
        logger.info("running_visual_regression_test", url=url)
        browser = BrowserAutomation()
        await browser.start()

        try:
            tester = VisualRegressionTester(str(VAULT_PATH / "Baselines"))
            result = await tester.test_visual_regression(browser, url)
            self.results["visual_regression"] = result
            return self.results

        finally:
            await browser.close()

    async def _run_performance_test(self, url: str) -> Dict[str, Any]:
        """Run performance test."""
        logger.info("running_performance_test", url=url)
        browser = BrowserAutomation()
        await browser.start()

        try:
            tester = PerformanceTester()
            result = await tester.test_performance(browser, url)
            self.results["performance"] = result
            return self.results

        finally:
            await browser.close()

    async def _run_api_contract_test(self, url: str) -> Dict[str, Any]:
        """Run API contract test."""
        logger.info("running_api_contract_test", url=url)

        tester = APIContractTester()
        schema_path = self._parse_schema_path()

        if schema_path and os.path.exists(schema_path):
            tester.load_schema(schema_path)

        # For API tests, we test common endpoints
        endpoints = [
            ("/health", "GET", None),
            ("/api/v1/status", "GET", None),
        ]

        for endpoint, method, body in endpoints:
            try:
                result = await tester.test_endpoint(url, endpoint, method, body)
                self.results[f"api_{endpoint.replace('/', '_')}"] = result
            except Exception as e:
                logger.error("api_test_error", endpoint=endpoint, error=str(e))

        return self.results

    async def _run_accessibility_test(self, url: str) -> Dict[str, Any]:
        """Run accessibility test."""
        logger.info("running_accessibility_test", url=url)
        browser = BrowserAutomation()
        await browser.start()

        try:
            tester = AccessibilityTester()
            result = await tester.test_accessibility(browser, url)
            self.results["accessibility"] = result
            return self.results

        finally:
            await browser.close()

    async def _run_multi_browser_test(self, url: str) -> Dict[str, Any]:
        """Run multi-browser test."""
        logger.info("running_multi_browser_test", url=url)

        tester = MultiBrowserTester()

        async def test_browser(browser, test_url):
            # Simple smoke test
            result = await browser.visit(test_url)
            return {
                "status": "pass" if result["success"] else "fail",
                "findings": [],
                "metrics": {"http_status": result.get("status")},
            }

        result = await tester.test_all_browsers(url, test_browser)
        self.results["multi_browser"] = result
        return self.results

    async def run(self) -> None:
        """Execute the feature test based on role."""
        logger.info("feature_tester_started", agent_id=self.agent_id, role=self.role)

        url = self._parse_url()
        if not url:
            logger.error("no_url_found_in_objective", objective=self.objective)
            await self._save_results({"status": "error", "error": "No URL found in objective"})
            return

        try:
            # Route to appropriate test based on role
            if self.role == "auth_tester":
                await self._run_auth_test(url)
            elif self.role == "visual_regression_tester":
                await self._run_visual_regression_test(url)
            elif self.role == "performance_tester":
                await self._run_performance_test(url)
            elif self.role == "api_contract_tester":
                await self._run_api_contract_test(url)
            elif self.role == "accessibility_tester":
                await self._run_accessibility_test(url)
            elif self.role == "multi_browser_tester":
                await self._run_multi_browser_test(url)
            else:
                logger.error("unknown_role", role=self.role)
                self.results = {"status": "error", "error": f"Unknown role: {self.role}"}

            await self._save_results(self.results)
            logger.info("feature_tester_completed", agent_id=self.agent_id, role=self.role)

        except Exception as e:
            logger.error("feature_tester_error", agent_id=self.agent_id, error=str(e))
            await self._save_results({"status": "error", "error": str(e)})

    async def _save_results(self, results: Dict[str, Any]) -> None:
        """Save test results to vault."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()

        # Determine overall status
        if "error" in results and not any(k != "error" for k in results.keys()):
            status = "fail"
        else:
            # Check if any individual test failed
            has_failures = False
            for key, value in results.items():
                if isinstance(value, dict) and value.get("status") == "fail":
                    has_failures = True
                    break
            status = "warning" if has_failures else "pass"

        # Build findings summary
        findings_summary = []
        for test_name, test_result in results.items():
            if isinstance(test_result, dict) and "findings" in test_result:
                for finding in test_result["findings"]:
                    findings_summary.append(
                        f"- [{finding.get('severity', 'info').upper()}] {finding.get('title', 'Unknown')}: {finding.get('description', '')}"
                    )

        # Build metrics summary
        metrics_summary = []
        for test_name, test_result in results.items():
            if isinstance(test_result, dict) and "metrics" in test_result:
                for metric_name, metric_value in test_result["metrics"].items():
                    metrics_summary.append(f"- {test_name}.{metric_name}: {metric_value}")

        content = f"""# Feature Test Results

## Agent
- **ID**: {self.agent_id}
- **Role**: {self.role}
- **Objective**: {self.objective}

## Status
- **Overall**: {status}
- **Started**: {timestamp}
- **Duration**: {elapsed:.2f}s

## Results
```json
{json.dumps(results, indent=2, default=str)}
```

## Findings
{chr(10).join(findings_summary) if findings_summary else "No findings recorded."}

## Metrics
{chr(10).join(metrics_summary) if metrics_summary else "No metrics recorded."}
"""

        self.vault.write_node(
            self.memory_node,
            content,
            frontmatter={
                "agent_id": self.agent_id,
                "role": self.role,
                "status": status,
                "started_at": timestamp,
                "duration_seconds": elapsed,
                "url": url if "url" in dir() else None,
            },
        )


async def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: worker.py <agent_id> <memory_node_path>")
        sys.exit(1)

    agent_id = sys.argv[1]
    memory_node = sys.argv[2]

    worker = FeatureTesterWorker(agent_id, memory_node)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
