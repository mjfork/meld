"""Unit tests for provider adapters."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meld.data_models import ProviderErrorType
from meld.providers.base import ProviderAdapter
from meld.providers.claude import ClaudeAdapter
from meld.providers.gemini import GeminiAdapter
from meld.providers.openai import OpenAIAdapter
from tests.mocks.mock_adapter import MockAdapter, MockAdapterFactory


class TestMockAdapter:
    """Tests for MockAdapter functionality."""

    @pytest.mark.asyncio
    async def test_default_response(self) -> None:
        """Mock adapter returns default response."""
        adapter = MockAdapter()

        result = await adapter.invoke("Create a plan")

        assert result.success is True
        assert result.provider == "mock"
        assert "Mock plan" in result.feedback or "Improvements" in result.feedback

    @pytest.mark.asyncio
    async def test_custom_response(self) -> None:
        """Mock adapter can return custom responses."""
        adapter = MockAdapter()
        adapter.set_responses({"custom": "Custom response content"})

        result = await adapter.invoke("custom prompt")

        assert result.success is True
        assert "Custom response content" in result.feedback

    @pytest.mark.asyncio
    async def test_tracks_invocations(self) -> None:
        """Mock adapter tracks all invocations."""
        adapter = MockAdapter()

        await adapter.invoke("First prompt")
        await adapter.invoke("Second prompt")

        assert adapter.invocation_count == 2
        assert "First prompt" in adapter.invocations
        assert "Second prompt" in adapter.invocations

    @pytest.mark.asyncio
    async def test_was_called_with(self) -> None:
        """Can check if adapter was called with specific content."""
        adapter = MockAdapter()

        await adapter.invoke("Prompt with authentication")

        assert adapter.was_called_with("authentication") is True
        assert adapter.was_called_with("nonexistent") is False

    @pytest.mark.asyncio
    async def test_fail_after(self) -> None:
        """Mock adapter can fail after N invocations."""
        adapter = MockAdapter()
        adapter.set_fail_after(2)

        result1 = await adapter.invoke("First")
        result2 = await adapter.invoke("Second")
        result3 = await adapter.invoke("Third")

        assert result1.success is True
        assert result2.success is True
        assert result3.success is False

    @pytest.mark.asyncio
    async def test_timeout_simulation(self) -> None:
        """Mock adapter can simulate timeout."""
        adapter = MockAdapter()
        adapter.set_timeout(True)

        result = await adapter.invoke("Prompt")

        assert result.success is False
        assert result.error is not None
        assert result.error.error_type == ProviderErrorType.TIMEOUT

    @pytest.mark.asyncio
    async def test_error_simulation(self) -> None:
        """Mock adapter can simulate specific errors."""
        adapter = MockAdapter()
        adapter.set_error(ProviderErrorType.AUTH_FAILED)

        result = await adapter.invoke("Prompt")

        assert result.success is False
        assert result.error is not None
        assert result.error.error_type == ProviderErrorType.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_reset(self) -> None:
        """Mock adapter can be reset."""
        adapter = MockAdapter()
        adapter.set_timeout(True)
        await adapter.invoke("Prompt")

        adapter.reset()

        assert adapter.invocation_count == 0
        result = await adapter.invoke("New prompt")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_streaming(self) -> None:
        """Mock adapter supports streaming."""
        adapter = MockAdapter()
        adapter.set_delay(0.01)

        chunks = []
        async for event in adapter.invoke_streaming("Prompt"):
            chunks.append(event)

        assert len(chunks) > 0
        assert chunks[-1].is_complete is True


class TestMockAdapterFactory:
    """Tests for MockAdapterFactory."""

    @pytest.mark.asyncio
    async def test_create_successful(self) -> None:
        """Factory creates successful adapter."""
        adapter = MockAdapterFactory.create_successful("test")

        result = await adapter.invoke("Prompt")

        assert result.success is True
        assert adapter.name == "test"

    @pytest.mark.asyncio
    async def test_create_failing(self) -> None:
        """Factory creates failing adapter."""
        adapter = MockAdapterFactory.create_failing("test", ProviderErrorType.NETWORK_ERROR)

        result = await adapter.invoke("Prompt")

        assert result.success is False
        assert result.error.error_type == ProviderErrorType.NETWORK_ERROR

    @pytest.mark.asyncio
    async def test_create_timeout(self) -> None:
        """Factory creates timeout adapter."""
        adapter = MockAdapterFactory.create_timeout("test")

        result = await adapter.invoke("Prompt")

        assert result.success is False
        assert result.error.error_type == ProviderErrorType.TIMEOUT

    @pytest.mark.asyncio
    async def test_create_flaky(self) -> None:
        """Factory creates flaky adapter."""
        adapter = MockAdapterFactory.create_flaky("test", fail_after=1)

        result1 = await adapter.invoke("First")
        result2 = await adapter.invoke("Second")

        assert result1.success is True
        assert result2.success is False


class TestClaudeAdapter:
    """Tests for ClaudeAdapter."""

    def test_name(self) -> None:
        """Adapter has correct name."""
        adapter = ClaudeAdapter()
        assert adapter.name == "claude"

    def test_cli_command(self) -> None:
        """Adapter has correct CLI command."""
        adapter = ClaudeAdapter()
        assert adapter.cli_command == "claude"

    def test_build_command(self) -> None:
        """Builds correct CLI command with all required flags."""
        adapter = ClaudeAdapter()
        cmd = adapter.build_command("Test prompt")

        # Verify all required flags are present
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "Test prompt" in cmd
        assert "--permission-mode" in cmd
        assert "plan" in cmd
        assert "--model" in cmd
        assert "opus" in cmd
        assert "--output-format" in cmd
        assert "text" in cmd

    def test_build_command_custom_model(self) -> None:
        """Can specify custom model."""
        adapter = ClaudeAdapter(model="sonnet")
        cmd = adapter.build_command("Test prompt")

        assert "--model" in cmd
        assert "sonnet" in cmd

    def test_classify_auth_error(self) -> None:
        """Correctly classifies Claude auth errors."""
        adapter = ClaudeAdapter()

        error = adapter._classify_error("Error: not logged in")
        assert error.error_type == ProviderErrorType.AUTH_FAILED

        error = adapter._classify_error("Please run claude auth")
        assert error.error_type == ProviderErrorType.AUTH_FAILED

    def test_classify_rate_limit_error(self) -> None:
        """Correctly classifies Claude rate limit errors."""
        adapter = ClaudeAdapter()

        error = adapter._classify_error("Error: rate limit exceeded")
        assert error.error_type == ProviderErrorType.RATE_LIMITED
        assert error.retryable is True

        error = adapter._classify_error("Error: 429 Too Many Requests")
        assert error.error_type == ProviderErrorType.RATE_LIMITED

    def test_classify_network_error(self) -> None:
        """Correctly classifies Claude network errors."""
        adapter = ClaudeAdapter()

        error = adapter._classify_error("Error: connection refused")
        assert error.error_type == ProviderErrorType.NETWORK_ERROR
        assert error.retryable is True

        error = adapter._classify_error("Error: ECONNREFUSED")
        assert error.error_type == ProviderErrorType.NETWORK_ERROR

    @pytest.mark.asyncio
    async def test_check_auth_when_not_available(self) -> None:
        """Auth check returns False when CLI not available."""
        adapter = ClaudeAdapter()

        with patch("shutil.which", return_value=None):
            result = await adapter.check_auth()
            # When CLI not found, check_auth will fail
            assert result is False or adapter.is_available() is False


class TestGeminiAdapter:
    """Tests for GeminiAdapter."""

    def test_name(self) -> None:
        """Adapter has correct name."""
        adapter = GeminiAdapter()
        assert adapter.name == "gemini"

    def test_cli_command(self) -> None:
        """Adapter has correct CLI command."""
        adapter = GeminiAdapter()
        assert adapter.cli_command == "gemini"

    def test_build_command(self) -> None:
        """Builds correct CLI command with all required flags."""
        adapter = GeminiAdapter()
        cmd = adapter.build_command("Test prompt")

        # Verify all required flags are present
        assert cmd[0] == "gemini"
        assert "-p" in cmd
        assert "Test prompt" in cmd
        assert "-m" in cmd
        assert "gemini-2.5-pro" in cmd
        assert "--sandbox" in cmd

    def test_build_command_custom_model(self) -> None:
        """Can specify custom model."""
        adapter = GeminiAdapter(model="gemini-2.0-flash")
        cmd = adapter.build_command("Test prompt")

        assert "-m" in cmd
        assert "gemini-2.0-flash" in cmd

    def test_classify_auth_error(self) -> None:
        """Correctly classifies Gemini auth errors."""
        adapter = GeminiAdapter()

        error = adapter._classify_error("Error: UNAUTHENTICATED")
        assert error.error_type == ProviderErrorType.AUTH_FAILED

        error = adapter._classify_error("Error: permission denied")
        assert error.error_type == ProviderErrorType.AUTH_FAILED

    def test_classify_rate_limit_error(self) -> None:
        """Correctly classifies Gemini rate limit errors."""
        adapter = GeminiAdapter()

        error = adapter._classify_error("Error: RESOURCE_EXHAUSTED")
        assert error.error_type == ProviderErrorType.RATE_LIMITED
        assert error.retryable is True

        error = adapter._classify_error("Error: quota exceeded")
        assert error.error_type == ProviderErrorType.RATE_LIMITED

    def test_classify_network_error(self) -> None:
        """Correctly classifies Gemini network errors."""
        adapter = GeminiAdapter()

        error = adapter._classify_error("Error: UNAVAILABLE")
        assert error.error_type == ProviderErrorType.NETWORK_ERROR
        assert error.retryable is True

        error = adapter._classify_error("Error: deadline exceeded")
        assert error.error_type == ProviderErrorType.NETWORK_ERROR


class TestOpenAIAdapter:
    """Tests for OpenAIAdapter."""

    def test_name(self) -> None:
        """Adapter has correct name."""
        adapter = OpenAIAdapter()
        assert adapter.name == "openai"

    def test_cli_command_prefers_codex(self) -> None:
        """Prefers codex CLI when available."""
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: "/usr/bin/codex" if x == "codex" else None

            adapter = OpenAIAdapter()
            assert adapter.cli_command == "codex"

    def test_cli_command_falls_back_to_chatgpt(self) -> None:
        """Falls back to chatgpt when codex not available."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None

            adapter = OpenAIAdapter()
            assert adapter.cli_command == "chatgpt"

    def test_build_command_codex(self) -> None:
        """Builds correct CLI command for codex with exec subcommand."""
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: "/usr/bin/codex" if x == "codex" else None

            adapter = OpenAIAdapter()
            cmd = adapter.build_command("Test prompt")

            # Verify codex-specific flags
            assert cmd[0] == "codex"
            assert "exec" in cmd
            assert "Test prompt" in cmd
            assert "--sandbox" in cmd
            assert "read-only" in cmd
            assert "--model" in cmd
            assert "gpt-5.2" in cmd

    def test_build_command_chatgpt_fallback(self) -> None:
        """Builds correct CLI command for chatgpt fallback."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None

            adapter = OpenAIAdapter()
            cmd = adapter.build_command("Test prompt")

            # Verify chatgpt fallback (no exec subcommand)
            assert cmd[0] == "chatgpt"
            assert "exec" not in cmd
            assert "Test prompt" in cmd
            assert "--model" in cmd
            assert "gpt-5.2" in cmd

    def test_build_command_custom_model(self) -> None:
        """Can specify custom model."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None

            adapter = OpenAIAdapter(model="gpt-4o")
            cmd = adapter.build_command("Test prompt")

            assert "--model" in cmd
            assert "gpt-4o" in cmd

    def test_classify_auth_error(self) -> None:
        """Correctly classifies OpenAI auth errors."""
        adapter = OpenAIAdapter()

        error = adapter._classify_error("Error: invalid api key")
        assert error.error_type == ProviderErrorType.AUTH_FAILED

        error = adapter._classify_error("Error: OPENAI_API_KEY not set")
        assert error.error_type == ProviderErrorType.AUTH_FAILED

    def test_classify_rate_limit_error(self) -> None:
        """Correctly classifies OpenAI rate limit errors."""
        adapter = OpenAIAdapter()

        error = adapter._classify_error("Error: too many requests")
        assert error.error_type == ProviderErrorType.RATE_LIMITED
        assert error.retryable is True

        error = adapter._classify_error("Error: insufficient quota")
        assert error.error_type == ProviderErrorType.RATE_LIMITED

    def test_classify_network_error(self) -> None:
        """Correctly classifies OpenAI network errors."""
        adapter = OpenAIAdapter()

        error = adapter._classify_error("Error: ECONNREFUSED")
        assert error.error_type == ProviderErrorType.NETWORK_ERROR
        assert error.retryable is True


class TestProviderAdapterBase:
    """Tests for base ProviderAdapter behavior."""

    @pytest.mark.asyncio
    async def test_invoke_when_cli_not_found(self) -> None:
        """Returns error when CLI not found."""
        adapter = ClaudeAdapter()

        with patch.object(adapter, "is_available", return_value=False):
            result = await adapter.invoke("Test prompt")

        assert result.success is False
        assert result.error is not None
        assert result.error.error_type == ProviderErrorType.CLI_NOT_FOUND

    @pytest.mark.asyncio
    async def test_classify_auth_error(self) -> None:
        """Correctly classifies authentication errors."""
        adapter = ClaudeAdapter()

        error = adapter._classify_error("Error: unauthorized - invalid API key")

        assert error.error_type == ProviderErrorType.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_classify_rate_limit_error(self) -> None:
        """Correctly classifies rate limit errors."""
        adapter = ClaudeAdapter()

        error = adapter._classify_error("Error: rate limit exceeded")

        assert error.error_type == ProviderErrorType.RATE_LIMITED
        assert error.retryable is True

    @pytest.mark.asyncio
    async def test_classify_network_error(self) -> None:
        """Correctly classifies network errors."""
        adapter = ClaudeAdapter()

        error = adapter._classify_error("Error: connection refused")

        assert error.error_type == ProviderErrorType.NETWORK_ERROR
        assert error.retryable is True
