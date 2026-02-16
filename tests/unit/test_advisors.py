"""Unit tests for advisor pool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meld.advisors import AdvisorPool
from meld.data_models import AdvisorResult, ProviderError, ProviderErrorType


class TestAdvisorPool:
    """Tests for AdvisorPool."""

    @pytest.fixture
    def mock_adapters(self):
        """Create mock adapters for all providers."""
        with patch("meld.advisors.ClaudeAdapter") as MockClaude, \
             patch("meld.advisors.GeminiAdapter") as MockGemini, \
             patch("meld.advisors.OpenAIAdapter") as MockOpenAI:

            claude = MockClaude.return_value
            claude.name = "claude"
            claude.invoke = AsyncMock(return_value=AdvisorResult(
                provider="claude", success=True, feedback="Claude feedback"
            ))

            gemini = MockGemini.return_value
            gemini.name = "gemini"
            gemini.invoke = AsyncMock(return_value=AdvisorResult(
                provider="gemini", success=True, feedback="Gemini feedback"
            ))

            openai = MockOpenAI.return_value
            openai.name = "openai"
            openai.invoke = AsyncMock(return_value=AdvisorResult(
                provider="openai", success=True, feedback="OpenAI feedback"
            ))

            yield {"claude": claude, "gemini": gemini, "openai": openai}

    @pytest.mark.asyncio
    async def test_collects_feedback_from_all_advisors(self, mock_adapters) -> None:
        """Collects feedback from all three advisors."""
        pool = AdvisorPool()

        results = await pool.collect_feedback(
            plan="Test plan",
            task="Test task",
            round_number=1,
        )

        assert len(results) == 3
        providers = {r.provider for r in results}
        assert "claude" in providers
        assert "gemini" in providers
        assert "openai" in providers

    @pytest.mark.asyncio
    async def test_feedback_includes_round_number(self, mock_adapters) -> None:
        """Results include the round number."""
        pool = AdvisorPool()

        results = await pool.collect_feedback(
            plan="Test plan",
            task="Test task",
            round_number=3,
        )

        for result in results:
            assert result.round_number == 3

    @pytest.mark.asyncio
    async def test_handles_advisor_failure(self, mock_adapters) -> None:
        """Handles failed advisor gracefully."""
        mock_adapters["gemini"].invoke = AsyncMock(
            return_value=AdvisorResult(
                provider="gemini",
                success=False,
                error=ProviderError(
                    error_type=ProviderErrorType.TIMEOUT,
                    message="Timeout",
                    provider="gemini",
                ),
            )
        )

        pool = AdvisorPool()
        results = await pool.collect_feedback(
            plan="Test plan",
            task="Test task",
            round_number=1,
        )

        assert len(results) == 3
        gemini_result = next(r for r in results if r.provider == "gemini")
        assert gemini_result.success is False

    @pytest.mark.asyncio
    async def test_retries_timeout_once(self, mock_adapters) -> None:
        """Retries timeout errors once."""
        call_count = 0

        async def flaky_invoke(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AdvisorResult(
                    provider="gemini",
                    success=False,
                    error=ProviderError(
                        error_type=ProviderErrorType.TIMEOUT,
                        message="Timeout",
                        provider="gemini",
                        retryable=True,
                    ),
                )
            return AdvisorResult(
                provider="gemini",
                success=True,
                feedback="Retry succeeded",
            )

        mock_adapters["gemini"].invoke = flaky_invoke

        pool = AdvisorPool()
        results = await pool.collect_feedback(
            plan="Test plan",
            task="Test task",
            round_number=1,
        )

        gemini_result = next(r for r in results if r.provider == "gemini")
        assert gemini_result.success is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retries_rate_limit_with_backoff(self, mock_adapters) -> None:
        """Retries rate limit errors with exponential backoff."""
        call_count = 0

        async def rate_limited_invoke(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return AdvisorResult(
                    provider="claude",
                    success=False,
                    error=ProviderError(
                        error_type=ProviderErrorType.RATE_LIMITED,
                        message="Rate limited",
                        provider="claude",
                        retryable=True,
                    ),
                )
            return AdvisorResult(
                provider="claude",
                success=True,
                feedback="Eventually succeeded",
            )

        mock_adapters["claude"].invoke = rate_limited_invoke

        pool = AdvisorPool()
        results = await pool.collect_feedback(
            plan="Test plan",
            task="Test task",
            round_number=1,
        )

        claude_result = next(r for r in results if r.provider == "claude")
        assert claude_result.success is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_for_auth_failure(self, mock_adapters) -> None:
        """Does not retry auth failures."""
        mock_adapters["openai"].invoke = AsyncMock(
            return_value=AdvisorResult(
                provider="openai",
                success=False,
                error=ProviderError(
                    error_type=ProviderErrorType.AUTH_FAILED,
                    message="Auth failed",
                    provider="openai",
                    retryable=False,
                ),
            )
        )

        pool = AdvisorPool()
        results = await pool.collect_feedback(
            plan="Test plan",
            task="Test task",
            round_number=1,
        )

        openai_result = next(r for r in results if r.provider == "openai")
        assert openai_result.success is False
        assert mock_adapters["openai"].invoke.call_count == 1

    @pytest.mark.asyncio
    async def test_status_change_callback(self, mock_adapters) -> None:
        """Calls status change callback."""
        status_changes: list[tuple[str, str]] = []

        def on_status(provider: str, status: str) -> None:
            status_changes.append((provider, status))

        pool = AdvisorPool(on_status_change=on_status)
        await pool.collect_feedback(
            plan="Test plan",
            task="Test task",
            round_number=1,
        )

        # Should have running and complete for each advisor
        running_count = sum(1 for _, s in status_changes if s == "running")
        complete_count = sum(1 for _, s in status_changes if s == "complete")

        assert running_count == 3
        assert complete_count == 3

    def test_get_participating_advisors(self, mock_adapters) -> None:
        """Returns list of successful advisors."""
        pool = AdvisorPool()

        results = [
            AdvisorResult(provider="claude", success=True, feedback=""),
            AdvisorResult(provider="gemini", success=False, feedback=""),
            AdvisorResult(provider="openai", success=True, feedback=""),
        ]

        participants = pool.get_participating_advisors(results)

        assert participants == ["claude", "openai"]

    def test_advisor_names(self) -> None:
        """Returns list of all advisor names."""
        with patch("meld.advisors.ClaudeAdapter") as MockClaude, \
             patch("meld.advisors.GeminiAdapter") as MockGemini, \
             patch("meld.advisors.OpenAIAdapter") as MockOpenAI:
            MockClaude.return_value.name = "claude"
            MockGemini.return_value.name = "gemini"
            MockOpenAI.return_value.name = "openai"

            pool = AdvisorPool()
            names = pool.advisor_names

            assert "claude" in names
            assert "gemini" in names
            assert "openai" in names
