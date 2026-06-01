"""
Unit tests for mcp_server/features/api_contract.py.
"""

import pytest
import json
import yaml
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

from mcp_server.features.api_contract import APIContractTester


@pytest.mark.unit
class TestAPIContractTester:
    """Tests for APIContractTester."""

    @pytest.fixture
    def tester(self):
        return APIContractTester()

    @pytest.fixture
    def sample_schema(self):
        return {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "id": {"type": "integer"},
                                                "name": {"type": "string"},
                                                "active": {"type": "boolean"},
                                                "score": {"type": "number"},
                                                "tags": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                            },
                                            "required": ["id", "name"],
                                        }
                                    }
                                },
                            },
                            "404": {"description": "Not Found"},
                        }
                    },
                    "post": {
                        "responses": {
                            "201": {"description": "Created"},
                        }
                    },
                },
                "/users/{id}": {
                    "get": {
                        "responses": {
                            "200": {"description": "OK"},
                        }
                    }
                },
            },
        }

    def test_init(self):
        """Should initialize with empty findings."""
        tester = APIContractTester()
        assert tester.findings == []
        assert tester.schema is None

    def test_load_schema_json(self, tester, tmp_path):
        """Should load JSON schema."""
        schema_path = tmp_path / "api.json"
        schema = {"openapi": "3.0.0", "info": {"title": "Test"}, "paths": {}}
        schema_path.write_text(json.dumps(schema))

        assert tester.load_schema(str(schema_path)) is True
        assert tester.schema == schema

    def test_load_schema_yaml(self, tester, tmp_path):
        """Should load YAML schema."""
        schema_path = tmp_path / "api.yaml"
        schema = {"openapi": "3.0.0", "info": {"title": "Test"}, "paths": {}}
        schema_path.write_text(yaml.dump(schema))

        assert tester.load_schema(str(schema_path)) is True
        assert tester.schema == schema

    def test_load_schema_yml_extension(self, tester, tmp_path):
        """Should load .yml schema."""
        schema_path = tmp_path / "api.yml"
        schema = {"openapi": "3.0.0", "info": {"title": "Test"}, "paths": {}}
        schema_path.write_text(yaml.dump(schema))

        assert tester.load_schema(str(schema_path)) is True

    def test_load_schema_not_found(self, tester, tmp_path):
        """Should return False when schema file not found."""
        result = tester.load_schema(str(tmp_path / "nonexistent.json"))
        assert result is False
        assert tester.schema is None

    def test_load_schema_invalid_json(self, tester, tmp_path):
        """Should return False for invalid JSON."""
        schema_path = tmp_path / "bad.json"
        schema_path.write_text("{not json}")

        result = tester.load_schema(str(schema_path))
        assert result is False

    def test_load_schema_invalid_yaml(self, tester, tmp_path):
        """Should return False for invalid YAML."""
        schema_path = tmp_path / "bad.yaml"
        # Write something that will cause yaml.safe_load to fail
        schema_path.write_text("{[unclosed")

        result = tester.load_schema(str(schema_path))
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_response_no_schema(self, tester):
        """Should fail when no schema is loaded."""
        browser = Mock()
        browser.network_logs = []

        result = await tester.validate_response(browser, "/users", "GET")

        assert result["status"] == "fail"
        assert any("No Schema Loaded" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_validate_response_no_matching_logs(self, tester, sample_schema):
        """Should return warning when no matching network logs."""
        tester.schema = sample_schema
        browser = Mock()
        browser.network_logs = [{"url": "/other", "method": "GET", "status": 200, "headers": {}}]

        result = await tester.validate_response(browser, "/users", "GET")

        assert result["status"] == "warning"
        assert any("No Matching Requests" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_validate_response_success(self, tester, sample_schema):
        """Should validate matching requests successfully."""
        tester.schema = sample_schema
        browser = Mock()
        browser.network_logs = [
            {
                "url": "https://api.example.com/users",
                "method": "GET",
                "status": 200,
                "headers": {"content-type": "application/json"},
            }
        ]

        result = await tester.validate_response(browser, "/users", "GET")

        assert result["status"] == "pass"
        assert result["requests_validated"] == 1
        assert result["requests_failed"] == 0
        assert result["total_requests"] == 1

    @pytest.mark.asyncio
    async def test_validate_response_unexpected_status(self, tester, sample_schema):
        """Should flag unexpected status codes."""
        tester.schema = sample_schema
        browser = Mock()
        browser.network_logs = [
            {
                "url": "https://api.example.com/users",
                "method": "GET",
                "status": 500,
                "headers": {"content-type": "application/json"},
            }
        ]

        result = await tester.validate_response(browser, "/users", "GET")

        assert result["status"] == "fail"
        assert result["requests_failed"] == 1
        assert any("Unexpected Status Code" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_validate_response_path_not_in_schema(self, tester, sample_schema):
        """Should flag paths not found in schema."""
        tester.schema = sample_schema
        browser = Mock()
        browser.network_logs = [
            {
                "url": "https://api.example.com/unknown",
                "method": "GET",
                "status": 200,
                "headers": {"content-type": "application/json"},
            }
        ]

        result = await tester.validate_response(browser, "/unknown", "GET")

        assert result["status"] == "warning"
        assert any("Path Not in Schema" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_validate_response_missing_content_type(self, tester, sample_schema):
        """Should flag missing application/json content type."""
        tester.schema = sample_schema
        browser = Mock()
        browser.network_logs = [
            {
                "url": "https://api.example.com/users",
                "method": "GET",
                "status": 200,
                "headers": {"content-type": "text/html"},
            }
        ]

        result = await tester.validate_response(browser, "/users", "GET")

        assert result["status"] == "pass"  # Status is OK, just a medium finding
        assert any("Missing Content-Type" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_validate_response_error_status_no_content_check(self, tester, sample_schema):
        """Should not check content-type for error status codes."""
        tester.schema = sample_schema
        browser = Mock()
        browser.network_logs = [
            {
                "url": "https://api.example.com/users",
                "method": "GET",
                "status": 404,
                "headers": {"content-type": "text/html"},
            }
        ]

        result = await tester.validate_response(browser, "/users", "GET")

        assert not any("Missing Content-Type" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_validate_response_exception(self, tester, sample_schema):
        """Should handle exceptions during validation."""
        tester.schema = sample_schema
        browser = Mock()
        browser.network_logs = None  # Will cause exception on iteration

        result = await tester.validate_response(browser, "/users", "GET")

        assert result["status"] == "fail"
        assert any("Validation Error" in f["title"] for f in result["findings"])

    def test_find_schema_path_exact_match(self, tester, sample_schema):
        """Should find exact path matches."""
        tester.schema = sample_schema

        assert tester._find_schema_path("https://api.example.com/users", "GET") == "/users"
        assert tester._find_schema_path("/users", "GET") == "/users"

    def test_find_schema_path_pattern_match(self, tester):
        """Should match paths with path parameters via regex."""
        tester.schema = {
            "paths": {
                "/items/{id}": {"get": {"responses": {}}},
            }
        }

        result = tester._find_schema_path("https://api.example.com/items/42", "GET")
        assert result == "/items/{id}"

    def test_find_schema_path_no_match(self, tester, sample_schema):
        """Should return None when no path matches."""
        tester.schema = sample_schema

        assert tester._find_schema_path("/nonexistent", "GET") is None

    def test_find_schema_path_no_schema(self, tester):
        """Should return None when no schema loaded."""
        assert tester._find_schema_path("/users", "GET") is None

    def test_get_expected_statuses(self, tester, sample_schema):
        """Should get expected status codes from schema."""
        tester.schema = sample_schema

        statuses = tester._get_expected_statuses("/users", "GET")
        assert 200 in statuses
        assert 404 in statuses

    def test_get_expected_statuses_no_schema(self, tester):
        """Should default to [200] when no schema."""
        assert tester._get_expected_statuses("/users", "GET") == [200]

    def test_get_expected_statuses_no_method(self, tester, sample_schema):
        """Should return empty list when method not in schema."""
        tester.schema = sample_schema
        assert tester._get_expected_statuses("/users", "DELETE") == []

    @pytest.mark.asyncio
    async def test_validate_response_body_no_schema(self, tester):
        """Should fail when no schema loaded."""
        result = await tester.validate_response_body({"name": "John"}, "/users", "GET", 200)
        assert result["status"] == "fail"

    @pytest.mark.asyncio
    async def test_validate_response_body_no_response_spec(self, tester, sample_schema):
        """Should return warning when no response spec."""
        tester.schema = sample_schema

        result = await tester.validate_response_body({"name": "John"}, "/users", "GET", 500)

        assert result["status"] == "warning"
        assert any("No Schema for Status Code" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_validate_response_body_no_json_schema(self, tester, sample_schema):
        """Should pass when no JSON schema defined."""
        # Add a path with no content schema
        tester.schema = {
            **sample_schema,
            "paths": {
                **sample_schema["paths"],
                "/health": {"get": {"responses": {"200": {"description": "OK"}}}},
            },
        }

        result = await tester.validate_response_body({}, "/health", "GET", 200)

        assert result["status"] == "pass"
        assert any("No JSON Schema" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_validate_response_body_valid(self, tester, sample_schema):
        """Should pass for valid response body."""
        tester.schema = sample_schema

        result = await tester.validate_response_body(
            {"id": 1, "name": "John", "active": True, "score": 95.5, "tags": ["a", "b"]},
            "/users",
            "GET",
            200,
        )

        assert result["status"] == "pass"
        assert len(result["findings"]) == 0

    @pytest.mark.asyncio
    async def test_validate_response_body_missing_required(self, tester, sample_schema):
        """Should fail for missing required fields."""
        tester.schema = sample_schema

        result = await tester.validate_response_body({"active": True}, "/users", "GET", 200)

        assert result["status"] == "fail"
        assert any("Missing Required Field" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_validate_response_body_type_mismatch_string(self, tester, sample_schema):
        """Should detect string type mismatch."""
        tester.schema = sample_schema

        result = await tester.validate_response_body({"id": 1, "name": 123}, "/users", "GET", 200)

        assert result["status"] == "fail"
        assert any(
            "Type Mismatch" in f["title"] and "string" in f["description"]
            for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_validate_response_body_type_mismatch_integer(self, tester, sample_schema):
        """Should detect integer type mismatch."""
        tester.schema = sample_schema

        result = await tester.validate_response_body(
            {"id": "not_an_int", "name": "John"}, "/users", "GET", 200
        )

        assert result["status"] == "fail"
        assert any(
            "Type Mismatch" in f["title"] and "integer" in f["description"]
            for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_validate_response_body_type_mismatch_number(self, tester, sample_schema):
        """Should detect number type mismatch."""
        tester.schema = sample_schema

        result = await tester.validate_response_body(
            {"id": 1, "name": "John", "score": "not_a_number"}, "/users", "GET", 200
        )

        assert result["status"] == "fail"
        assert any(
            "Type Mismatch" in f["title"] and "number" in f["description"]
            for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_validate_response_body_type_mismatch_boolean(self, tester, sample_schema):
        """Should detect boolean type mismatch."""
        tester.schema = sample_schema

        result = await tester.validate_response_body(
            {"id": 1, "name": "John", "active": "yes"}, "/users", "GET", 200
        )

        assert result["status"] == "fail"
        assert any(
            "Type Mismatch" in f["title"] and "boolean" in f["description"]
            for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_validate_response_body_array_validation(self, tester, sample_schema):
        """Should validate array items."""
        tester.schema = sample_schema

        result = await tester.validate_response_body(
            {"id": 1, "name": "John", "tags": ["a", 123, "c"]}, "/users", "GET", 200
        )

        assert result["status"] == "fail"
        assert any(
            "Type Mismatch" in f["title"] and "string" in f["description"]
            for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_validate_response_body_nested_object(self, tester):
        """Should validate nested object properties."""
        tester.schema = {
            "paths": {
                "/nested": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "user": {
                                                    "type": "object",
                                                    "properties": {
                                                        "name": {"type": "string"},
                                                    },
                                                    "required": ["name"],
                                                }
                                            },
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        result = await tester.validate_response_body(
            {"user": {"name": "John"}}, "/nested", "GET", 200
        )
        assert result["status"] == "pass"

        result = await tester.validate_response_body({"user": {}}, "/nested", "GET", 200)
        assert result["status"] == "fail"
        assert any(
            "Missing Required Field" in f["title"] and "root.user" in f["description"]
            for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_validate_response_body_exception(self, tester, sample_schema):
        """Should handle exceptions during body validation."""
        tester.schema = sample_schema

        with patch.object(tester, "_validate_value", side_effect=Exception("Validation crash")):
            result = await tester.validate_response_body({"id": 1}, "/users", "GET", 200)

        assert result["status"] == "fail"
        assert any("Validation Error" in f["title"] for f in result["findings"])

    def test_validate_value_object(self, tester):
        """Should validate object properties recursively."""
        tester.findings = []
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["name"],
        }

        tester._validate_value({"count": 5}, schema, "root")
        assert any("Missing Required Field" in f["title"] for f in tester.findings)

        tester.findings = []
        tester._validate_value({"name": 123, "count": 5}, schema, "root")
        assert any(
            "Type Mismatch" in f["title"] and "name" in f["description"] for f in tester.findings
        )

    def test_validate_value_array(self, tester):
        """Should validate array items."""
        tester.findings = []
        schema = {
            "type": "array",
            "items": {"type": "integer"},
        }

        tester._validate_value([1, 2, "three"], schema, "root")
        assert any(
            "Type Mismatch" in f["title"] and "root[2]" in f["description"] for f in tester.findings
        )

    def test_validate_value_no_type(self, tester):
        """Should not validate when schema has no type."""
        tester.findings = []
        tester._validate_value("anything", {}, "root")
        assert len(tester.findings) == 0

    def test_validate_value_unrecognized_type(self, tester):
        """Should not add findings for unrecognized schema types."""
        tester.findings = []
        tester._validate_value("value", {"type": "unknown"}, "root")
        assert len(tester.findings) == 0

    def test_build_result(self, tester):
        """Should build result with correct structure."""
        start = datetime.now(timezone.utc)
        result = tester._build_result("pass", start)

        assert result["status"] == "pass"
        assert result["findings"] == []
        assert "duration_seconds" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_validate_response_multiple_logs(self, tester, sample_schema):
        """Should validate multiple matching network logs."""
        tester.schema = sample_schema
        browser = Mock()
        browser.network_logs = [
            {
                "url": "https://api.example.com/users",
                "method": "GET",
                "status": 200,
                "headers": {"content-type": "application/json"},
            },
            {
                "url": "https://api.example.com/users?page=2",
                "method": "GET",
                "status": 200,
                "headers": {"content-type": "application/json"},
            },
        ]

        result = await tester.validate_response(browser, "/users", "GET")

        assert result["status"] == "pass"
        assert result["requests_validated"] == 2
        assert result["total_requests"] == 2

    @pytest.mark.asyncio
    async def test_validate_response_mixed_results(self, tester, sample_schema):
        """Should handle mix of pass and fail validations."""
        tester.schema = sample_schema
        browser = Mock()
        browser.network_logs = [
            {
                "url": "https://api.example.com/users",
                "method": "GET",
                "status": 200,
                "headers": {"content-type": "application/json"},
            },
            {
                "url": "https://api.example.com/users",
                "method": "GET",
                "status": 500,
                "headers": {"content-type": "application/json"},
            },
        ]

        result = await tester.validate_response(browser, "/users", "GET")

        assert result["status"] == "fail"
        assert result["requests_validated"] == 1
        assert result["requests_failed"] == 1

    @pytest.mark.asyncio
    async def test_test_endpoint(self, tester, sample_schema):
        """Should test endpoint via BrowserAutomation wrapper."""
        tester.schema = sample_schema

        mock_browser = AsyncMock()
        mock_browser.network_logs = [
            {
                "url": "https://api.example.com/users",
                "method": "GET",
                "status": 200,
                "headers": {"content-type": "application/json"},
            }
        ]

        with patch("mcp_server.browser_tools.BrowserAutomation") as MockBrowserAuto:
            MockBrowserAuto.return_value = mock_browser

            result = await tester.test_endpoint("https://api.example.com", "/users", "GET")

        assert result["status"] == "pass"
        mock_browser.start.assert_awaited_once()
        mock_browser.visit.assert_awaited_once_with("https://api.example.com/users")
        mock_browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_test_endpoint_with_body(self, tester, sample_schema):
        """Should pass body parameter to test_endpoint."""
        tester.schema = sample_schema

        mock_browser = AsyncMock()
        mock_browser.network_logs = []

        with patch("mcp_server.browser_tools.BrowserAutomation") as MockBrowserAuto:
            MockBrowserAuto.return_value = mock_browser

            result = await tester.test_endpoint(
                "https://api.example.com", "/users", "POST", body={"name": "John"}
            )

        # Body is accepted but not used directly in validate_response
        assert result["status"] == "warning"
