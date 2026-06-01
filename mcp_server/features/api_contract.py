"""
API contract testing using OpenAPI schema validation.
"""

import json
import yaml
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path

import structlog

logger = structlog.get_logger()


class APIContractTester:
    """Validates API responses against OpenAPI schemas."""

    def __init__(self):
        self.findings: List[Dict[str, Any]] = []
        self.schema: Optional[Dict[str, Any]] = None

    def load_schema(self, schema_path: str) -> bool:
        """
        Load OpenAPI schema from file.

        Args:
            schema_path: Path to OpenAPI YAML or JSON file

        Returns:
            True if schema loaded successfully
        """
        try:
            path = Path(schema_path)
            if not path.exists():
                logger.error("schema_not_found", path=schema_path)
                return False

            content = path.read_text()

            if path.suffix in [".yaml", ".yml"]:
                self.schema = yaml.safe_load(content)
            else:
                self.schema = json.loads(content)

            logger.info(
                "schema_loaded",
                path=schema_path,
                title=self.schema.get("info", {}).get("title", "Unknown"),
            )
            return True

        except Exception as e:
            logger.error("schema_load_error", error=str(e))
            return False

    async def validate_response(
        self, browser, url_pattern: str, method: str = "GET"
    ) -> Dict[str, Any]:
        """
        Validate intercepted API responses against schema.

        Args:
            browser: BrowserAutomation instance with network_logs
            url_pattern: URL pattern to match (e.g., "/api/users")
            method: HTTP method

        Returns:
            Validation results
        """
        self.findings = []
        start_time = datetime.now(timezone.utc)

        if not self.schema:
            self.findings.append(
                {
                    "title": "No Schema Loaded",
                    "description": "OpenAPI schema not loaded. Call load_schema() first.",
                    "severity": "critical",
                }
            )
            return self._build_result("fail", start_time)

        try:
            # Find matching requests in network logs
            matching_logs = [
                log
                for log in browser.network_logs
                if url_pattern in log.get("url", "") and log.get("method") == method
            ]

            if not matching_logs:
                self.findings.append(
                    {
                        "title": "No Matching Requests",
                        "description": f"No {method} requests to {url_pattern} found",
                        "severity": "warning",
                    }
                )
                return self._build_result("warning", start_time)

            # Validate each response
            validated_count = 0
            failed_count = 0

            for log in matching_logs:
                # Get response details
                status = log.get("status", 0)

                # Find matching schema path
                schema_path = self._find_schema_path(log.get("url", ""), method)

                if not schema_path:
                    self.findings.append(
                        {
                            "title": "Path Not in Schema",
                            "description": f"URL {log.get('url')} not found in OpenAPI schema",
                            "severity": "medium",
                        }
                    )
                    continue

                # Check status code
                expected_statuses = self._get_expected_statuses(schema_path, method)
                if status not in expected_statuses:
                    self.findings.append(
                        {
                            "title": "Unexpected Status Code",
                            "description": f"Got {status}, expected one of {expected_statuses}",
                            "severity": "high",
                        }
                    )
                    failed_count += 1
                else:
                    validated_count += 1

                # Check response headers
                headers = log.get("headers", {})
                content_type = headers.get("content-type", "")

                if "application/json" not in content_type and status < 400:
                    self.findings.append(
                        {
                            "title": "Missing Content-Type",
                            "description": f"Response Content-Type is '{content_type}', expected application/json",
                            "severity": "medium",
                        }
                    )

            # Build result
            if failed_count > 0:
                status = "fail"
            elif validated_count > 0:
                status = "pass"
            else:
                status = "warning"

            return {
                **self._build_result(status, start_time),
                "requests_validated": validated_count,
                "requests_failed": failed_count,
                "total_requests": len(matching_logs),
            }

        except Exception as e:
            logger.error("api_validation_error", error=str(e))
            self.findings.append(
                {"title": "Validation Error", "description": str(e), "severity": "critical"}
            )
            return self._build_result("fail", start_time)

    def _find_schema_path(self, url: str, method: str) -> Optional[str]:
        """Find matching path in OpenAPI schema."""
        if not self.schema:
            return None

        paths: Dict[str, Any] = self.schema.get("paths", {})

        # Try exact match first
        for path in paths:
            if path in url:
                return str(path)

        # Try pattern matching
        for path in paths:
            # Convert OpenAPI path params to regex
            # /users/{id} -> /users/[^/]+
            import re

            pattern = re.sub(r"\{[^}]+\}", "[^/]+", str(path))
            if re.search(pattern, url):
                return str(path)

        return None

    def _get_expected_statuses(self, path: str, method: str) -> List[int]:
        """Get expected HTTP status codes from schema."""
        if not self.schema:
            return [200]

        path_spec = self.schema.get("paths", {}).get(path, {})
        method_spec = path_spec.get(method.lower(), {})
        responses = method_spec.get("responses", {})

        return [int(code) for code in responses.keys() if code.isdigit()]

    async def validate_response_body(
        self, body: Dict[str, Any], path: str, method: str, status_code: int = 200
    ) -> Dict[str, Any]:
        """
        Validate response body against schema.

        Args:
            body: Response body as dict
            path: API path
            method: HTTP method
            status_code: HTTP status code

        Returns:
            Validation results
        """
        self.findings = []
        start_time = datetime.now(timezone.utc)

        if not self.schema:
            return self._build_result("fail", start_time)

        try:
            path_spec = self.schema.get("paths", {}).get(path, {})
            method_spec = path_spec.get(method.lower(), {})
            response_spec = method_spec.get("responses", {}).get(str(status_code), {})

            if not response_spec:
                self.findings.append(
                    {
                        "title": "No Schema for Status Code",
                        "description": f"No schema defined for {method} {path} {status_code}",
                        "severity": "warning",
                    }
                )
                return self._build_result("warning", start_time)

            # Get response schema
            content = response_spec.get("content", {})
            json_schema = content.get("application/json", {}).get("schema", {})

            if not json_schema:
                self.findings.append(
                    {
                        "title": "No JSON Schema",
                        "description": "Response schema not defined as application/json",
                        "severity": "info",
                    }
                )
                return self._build_result("pass", start_time)

            # Validate body against schema
            self._validate_value(body, json_schema, "root")

            status = (
                "fail"
                if any(f["severity"] in ["critical", "high"] for f in self.findings)
                else "pass"
            )

            return self._build_result(status, start_time)

        except Exception as e:
            self.findings.append(
                {"title": "Validation Error", "description": str(e), "severity": "critical"}
            )
            return self._build_result("fail", start_time)

    def _validate_value(self, value: Any, schema: Dict[str, Any], path: str):
        """Recursively validate a value against schema."""
        schema_type = schema.get("type")

        if schema_type == "object" and isinstance(value, dict):
            properties = schema.get("properties", {})
            required = schema.get("required", [])

            # Check required fields
            for field in required:
                if field not in value:
                    self.findings.append(
                        {
                            "title": "Missing Required Field",
                            "description": f"Field '{field}' is required at {path}",
                            "severity": "high",
                        }
                    )

            # Validate properties
            for key, prop_schema in properties.items():
                if key in value:
                    self._validate_value(value[key], prop_schema, f"{path}.{key}")

        elif schema_type == "array" and isinstance(value, list):
            items_schema = schema.get("items", {})
            for i, item in enumerate(value):
                self._validate_value(item, items_schema, f"{path}[{i}]")

        elif schema_type == "string" and not isinstance(value, str):
            self.findings.append(
                {
                    "title": "Type Mismatch",
                    "description": f"Expected string at {path}, got {type(value).__name__}",
                    "severity": "high",
                }
            )

        elif schema_type == "integer" and not isinstance(value, int):
            self.findings.append(
                {
                    "title": "Type Mismatch",
                    "description": f"Expected integer at {path}, got {type(value).__name__}",
                    "severity": "high",
                }
            )

        elif schema_type == "number" and not isinstance(value, (int, float)):
            self.findings.append(
                {
                    "title": "Type Mismatch",
                    "description": f"Expected number at {path}, got {type(value).__name__}",
                    "severity": "high",
                }
            )

        elif schema_type == "boolean" and not isinstance(value, bool):
            self.findings.append(
                {
                    "title": "Type Mismatch",
                    "description": f"Expected boolean at {path}, got {type(value).__name__}",
                    "severity": "high",
                }
            )

    async def test_endpoint(
        self,
        base_url: str,
        endpoint: str,
        method: str = "GET",
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Test an API endpoint (wrapper for validate_response)."""
        from mcp_server.browser_tools import BrowserAutomation

        browser = BrowserAutomation()
        await browser.start()
        try:
            # Visit the endpoint to populate network logs
            url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            await browser.visit(url)
            return await self.validate_response(browser, endpoint, method)
        finally:
            await browser.close()

    def _build_result(self, status: str, start_time: datetime) -> Dict[str, Any]:
        """Build test result."""
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        return {
            "status": status,
            "findings": self.findings,
            "duration_seconds": elapsed,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        }
