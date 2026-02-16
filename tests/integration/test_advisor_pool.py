"""Integration tests for advisor pool with mock adapters."""

import pytest

from meld.data_models import ProviderErrorType
from tests.mocks.mock_adapter import MockAdapter, MockAdapterFactory


class TestAdvisorPoolWithMocks:
    """Integration tests using MockAdapter instead of real CLIs."""

    @pytest.mark.asyncio
    async def test_parallel_feedback_collection(self) -> None:
        """Tests collecting feedback from multiple mock adapters in parallel."""
        adapters = [
            MockAdapter(name="mock-claude", delay=0.05),
            MockAdapter(name="mock-gemini", delay=0.05),
            MockAdapter(name="mock-openai", delay=0.05),
        ]

        import asyncio
        import time

        start = time.monotonic()
        results = await asyncio.gather(*[
            adapter.invoke("Test prompt") for adapter in adapters
        ])
        duration = time.monotonic() - start

        # All should succeed
        assert all(r.success for r in results)

        # Should run in parallel (duration < sum of delays)
        assert duration < 0.15  # Would be ~0.15s sequential, should be ~0.05s parallel

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self) -> None:
        """Tests handling mix of successful and failed adapters."""
        adapters = [
            MockAdapterFactory.create_successful("success"),
            MockAdapterFactory.create_failing("failure", ProviderErrorType.TIMEOUT),
            MockAdapterFactory.create_successful("success2"),
        ]

        import asyncio

        results = await asyncio.gather(*[
            adapter.invoke("Test prompt") for adapter in adapters
        ])

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        assert len(successful) == 2
        assert len(failed) == 1
        assert failed[0].error.error_type == ProviderErrorType.TIMEOUT

    @pytest.mark.asyncio
    async def test_all_adapters_fail(self) -> None:
        """Tests graceful handling when all adapters fail."""
        adapters = [
            MockAdapterFactory.create_failing("fail1", ProviderErrorType.AUTH_FAILED),
            MockAdapterFactory.create_failing("fail2", ProviderErrorType.NETWORK_ERROR),
            MockAdapterFactory.create_timeout("fail3"),
        ]

        import asyncio

        results = await asyncio.gather(*[
            adapter.invoke("Test prompt") for adapter in adapters
        ])

        assert all(not r.success for r in results)
        error_types = {r.error.error_type for r in results}
        assert ProviderErrorType.AUTH_FAILED in error_types
        assert ProviderErrorType.NETWORK_ERROR in error_types
        assert ProviderErrorType.TIMEOUT in error_types

    @pytest.mark.asyncio
    async def test_streaming_from_multiple_adapters(self) -> None:
        """Tests streaming output from multiple adapters."""
        adapters = [
            MockAdapter(name="stream1", delay=0.01),
            MockAdapter(name="stream2", delay=0.01),
        ]

        async def collect_stream(adapter, prompt):
            chunks = []
            async for event in adapter.invoke_streaming(prompt):
                chunks.append(event)
            return chunks

        import asyncio

        results = await asyncio.gather(*[
            collect_stream(adapter, "Test prompt") for adapter in adapters
        ])

        # Both should have streamed output
        for chunks in results:
            assert len(chunks) > 0
            assert chunks[-1].is_complete

    @pytest.mark.asyncio
    async def test_invocation_tracking(self) -> None:
        """Tests that all adapters track their invocations."""
        adapters = [
            MockAdapter(name="track1"),
            MockAdapter(name="track2"),
        ]

        prompts = [
            "First prompt with authentication",
            "Second prompt about database",
            "Third prompt for testing",
        ]

        import asyncio

        for prompt in prompts:
            await asyncio.gather(*[
                adapter.invoke(prompt) for adapter in adapters
            ])

        for adapter in adapters:
            assert adapter.invocation_count == 3
            assert adapter.was_called_with("authentication")
            assert adapter.was_called_with("database")
            assert adapter.was_called_with("testing")


class TestAdapterRecovery:
    """Integration tests for adapter recovery scenarios."""

    @pytest.mark.asyncio
    async def test_flaky_adapter_recovery(self) -> None:
        """Tests adapter that fails initially but succeeds on retry."""
        call_count = 0

        async def flaky_invoke(prompt):
            from meld.data_models import AdvisorResult, ProviderError, ProviderErrorType

            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return AdvisorResult(
                    provider="flaky",
                    success=False,
                    error=ProviderError(
                        error_type=ProviderErrorType.NETWORK_ERROR,
                        message="Network hiccup",
                        provider="flaky",
                        retryable=True,
                    ),
                )
            return AdvisorResult(
                provider="flaky",
                success=True,
                feedback="Finally worked!",
            )

        adapter = MockAdapter(name="flaky")
        # Override invoke for this test
        original_invoke = adapter.invoke
        adapter.invoke = flaky_invoke

        # Simulate retry logic
        result = None
        for attempt in range(5):
            result = await adapter.invoke("Test prompt")
            if result.success:
                break

        assert result is not None
        assert result.success
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_adapter_timeout_handling(self) -> None:
        """Tests proper timeout handling."""
        import asyncio

        adapter = MockAdapter(name="slow")
        adapter.set_delay(0.5)  # 500ms delay

        # Use asyncio timeout
        try:
            result = await asyncio.wait_for(
                adapter.invoke("Test prompt"),
                timeout=0.1,  # 100ms timeout
            )
            assert False, "Should have timed out"
        except asyncio.TimeoutError:
            pass  # Expected

    @pytest.mark.asyncio
    async def test_adapter_reset_between_tests(self) -> None:
        """Tests that adapter can be reset between test scenarios."""
        adapter = MockAdapter(name="resettable")

        # First scenario: configure to fail
        adapter.set_error(ProviderErrorType.AUTH_FAILED)
        result1 = await adapter.invoke("Prompt 1")
        assert not result1.success

        # Reset and second scenario: should succeed
        adapter.reset()
        result2 = await adapter.invoke("Prompt 2")
        assert result2.success

        # Verify invocation count was reset
        assert adapter.invocation_count == 1
