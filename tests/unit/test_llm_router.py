"""
Unit tests for LLMRouter.
Uses mocked LLM clients to avoid real API calls.
"""

import pytest
import os
from unittest.mock import Mock, patch
from mcp_server.llm_router import LLMRouter, LLMResponse


class TestLLMRouterBasic:
    """Test basic LLM routing."""

    def test_parse_model_with_provider(self):
        """Should parse provider/model format."""
        router = LLMRouter.__new__(LLMRouter)
        provider, model = router._parse_model("openai/gpt-4o")
        assert provider == "openai"
        assert model == "gpt-4o"

    def test_parse_model_without_provider(self):
        """Should default to openai if no provider."""
        router = LLMRouter.__new__(LLMRouter)
        provider, model = router._parse_model("gpt-4")
        assert provider == "openai"
        assert model == "gpt-4"

    def test_uninitialized_provider(self):
        """Should raise error for uninitialized provider."""
        router = LLMRouter.__new__(LLMRouter)
        router.clients = {}

        with pytest.raises(ValueError) as exc_info:
            router.complete(model="openai/gpt-4o", messages=[{"role": "user", "content": "Hello"}])
        assert "not initialized" in str(exc_info.value)


class TestLLMRouterOpenAI:
    """Test OpenAI-compatible routing."""

    def test_openai_completion(self):
        """Should route to OpenAI client."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Hello"))]
        mock_response.usage = Mock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        mock_client.chat.completions.create.return_value = mock_response

        router = LLMRouter.__new__(LLMRouter)
        router.clients = {"openai": mock_client}

        result = router._openai_complete(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7,
            max_tokens=100,
        )

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello"
        assert result.model == "gpt-4o"
        assert result.provider == "openai"
        assert result.usage["total_tokens"] == 15


class TestLLMRouterAnthropic:
    """Test Anthropic routing."""

    def test_anthropic_completion(self):
        """Should route to Anthropic client."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = [Mock(text="Hello from Claude")]
        mock_response.usage = Mock(input_tokens=10, output_tokens=5)
        mock_client.messages.create.return_value = mock_response

        router = LLMRouter.__new__(LLMRouter)
        router.clients = {"anthropic": mock_client}

        result = router._anthropic_complete(
            model="claude-3-5-sonnet",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7,
            max_tokens=100,
        )

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello from Claude"
        assert result.provider == "anthropic"


class TestGetLLMResponse:
    """Test the convenience function."""

    @patch.dict(os.environ, {"UI_EXPLORER_MODEL": "anthropic/claude-3-5-sonnet"})
    def test_get_llm_response_for_role(self):
        """Should use role-specific model."""
        with patch("mcp_server.llm_router.llm_router") as mock_router:
            mock_response = Mock()
            mock_response.content = "Test response"
            mock_router.complete.return_value = mock_response

            from mcp_server.llm_router import get_llm_response

            result = get_llm_response(agent_role="ui_explorer", prompt="Test prompt")

            assert result == "Test response"
            mock_router.complete.assert_called_once()
            call_args = mock_router.complete.call_args
            assert call_args[1]["model"] == "anthropic/claude-3-5-sonnet"

    @patch.dict(os.environ, {}, clear=True)
    def test_get_llm_response_fallback(self):
        """Should fallback to default model."""
        with patch("mcp_server.llm_router.llm_router") as mock_router:
            mock_router.complete.side_effect = Exception("API Error")

            from mcp_server.llm_router import get_llm_response

            result = get_llm_response(agent_role="unknown_role", prompt="Test")

            assert "Error calling LLM" in result
