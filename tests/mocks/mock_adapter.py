"""Mock provider adapter for CI testing."""

import asyncio
from typing import AsyncIterator

from meld.data_models import (
    AdvisorResult,
    ProviderError,
    ProviderErrorType,
    StreamEvent,
)
from meld.providers.base import ProviderAdapter


class MockAdapter(ProviderAdapter):
    """Mock provider adapter for testing without real CLIs.

    This adapter simulates provider behavior for CI/CD testing where
    real CLIs are not available. It can be configured to return
    specific responses, simulate failures, and track invocations.
    """

    # Default mock responses
    DEFAULT_RESPONSES = {
        "plan": """## Overview
Mock plan generated for testing.

## Steps
1. Step one of the mock plan
2. Step two of the mock plan
3. Step three of the mock plan

## Considerations
- Mock consideration one
- Mock consideration two

## Risks
- Mock risk that should be addressed
""",
        "feedback": """## Improvements
- Consider adding error handling
- Add input validation

## Concerns
- Performance under load
- Edge case handling

## Additions
- Add logging for debugging
- Include metrics collection

## Rationale
These improvements will enhance reliability and maintainability.
""",
        "synthesis": """## Decision Log
- ACCEPTED: Add error handling - improves reliability
- ACCEPTED: Add input validation - prevents bugs
- DEFERRED: Performance optimization - not critical for v1

## Updated Plan
[Updated plan content here]

## Convergence Assessment
```json
{
    "STATUS": "CONTINUING",
    "CHANGES_MADE": 2,
    "OPEN_ITEMS": 1,
    "RATIONALE": "Incorporated feedback, one item remains"
}
```
""",
        "converged": """## Decision Log
- ACCEPTED: Minor wording improvements

## Updated Plan
[Final plan content]

## Convergence Assessment
```json
{
    "STATUS": "CONVERGED",
    "CHANGES_MADE": 0,
    "OPEN_ITEMS": 0,
    "RATIONALE": "No substantive changes needed"
}
```
""",
    }

    def __init__(
        self,
        name: str = "mock",
        timeout: int = 600,
        delay: float = 0.1,
    ) -> None:
        """Initialize mock adapter.

        Args:
            name: Name for this mock adapter
            timeout: Timeout (not used but kept for interface compatibility)
            delay: Simulated processing delay in seconds
        """
        super().__init__(timeout=timeout)
        self._name = name
        self._delay = delay
        self._responses: dict[str, str] = self.DEFAULT_RESPONSES.copy()
        self._invocations: list[str] = []
        self._fail_after: int | None = None
        self._invocation_count = 0
        self._should_timeout = False
        self._error_type: ProviderErrorType | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def cli_command(self) -> str:
        return "mock-cli"

    def is_available(self) -> bool:
        """Mock CLI is always available."""
        return True

    def build_command(self, prompt: str) -> list[str]:
        """Build mock command (not used)."""
        return ["mock-cli", prompt]

    async def check_auth(self) -> bool:
        """Mock auth always succeeds."""
        return True

    # ========================================================================
    # Configuration Methods
    # ========================================================================

    def set_responses(self, responses: dict[str, str]) -> None:
        """Set custom responses for specific prompts or types.

        Args:
            responses: Dict mapping prompt substrings or types to responses
        """
        self._responses.update(responses)

    def set_delay(self, delay: float) -> None:
        """Set the simulated processing delay."""
        self._delay = delay

    def set_fail_after(self, count: int) -> None:
        """Configure the adapter to fail after N invocations."""
        self._fail_after = count

    def set_timeout(self, should_timeout: bool = True) -> None:
        """Configure the adapter to simulate timeout."""
        self._should_timeout = should_timeout

    def set_error(self, error_type: ProviderErrorType) -> None:
        """Configure the adapter to return a specific error."""
        self._error_type = error_type

    def reset(self) -> None:
        """Reset the adapter state."""
        self._invocations = []
        self._invocation_count = 0
        self._should_timeout = False
        self._error_type = None
        self._fail_after = None

    # ========================================================================
    # Inspection Methods
    # ========================================================================

    @property
    def invocations(self) -> list[str]:
        """Get list of all prompts received."""
        return self._invocations.copy()

    @property
    def invocation_count(self) -> int:
        """Get total number of invocations."""
        return self._invocation_count

    def was_called_with(self, substring: str) -> bool:
        """Check if any invocation contained the given substring."""
        return any(substring in inv for inv in self._invocations)

    # ========================================================================
    # Invocation Methods
    # ========================================================================

    async def invoke(self, prompt: str) -> AdvisorResult:
        """Invoke the mock adapter."""
        import time

        start = time.monotonic()
        self._invocations.append(prompt)
        self._invocation_count += 1

        # Simulate processing delay
        await asyncio.sleep(self._delay)

        # Check for configured failures
        if self._fail_after is not None and self._invocation_count > self._fail_after:
            return AdvisorResult(
                provider=self._name,
                success=False,
                error=ProviderError(
                    error_type=ProviderErrorType.UNKNOWN,
                    message="Configured to fail after N invocations",
                    provider=self._name,
                ),
                duration_seconds=time.monotonic() - start,
            )

        if self._should_timeout:
            return AdvisorResult(
                provider=self._name,
                success=False,
                error=ProviderError(
                    error_type=ProviderErrorType.TIMEOUT,
                    message="Simulated timeout",
                    provider=self._name,
                    retryable=True,
                ),
                duration_seconds=time.monotonic() - start,
            )

        if self._error_type:
            return AdvisorResult(
                provider=self._name,
                success=False,
                error=ProviderError(
                    error_type=self._error_type,
                    message=f"Simulated {self._error_type.value} error",
                    provider=self._name,
                    retryable=self._error_type
                    in [
                        ProviderErrorType.TIMEOUT,
                        ProviderErrorType.RATE_LIMITED,
                        ProviderErrorType.NETWORK_ERROR,
                    ],
                ),
                duration_seconds=time.monotonic() - start,
            )

        # Determine response based on prompt content
        response = self._get_response_for_prompt(prompt)

        return AdvisorResult(
            provider=self._name,
            success=True,
            feedback=response,
            duration_seconds=time.monotonic() - start,
        )

    async def invoke_streaming(self, prompt: str) -> AsyncIterator[StreamEvent]:
        """Invoke with streaming output."""
        self._invocations.append(prompt)
        self._invocation_count += 1

        response = self._get_response_for_prompt(prompt)

        # Stream response line by line
        for line in response.split("\n"):
            await asyncio.sleep(self._delay / 10)
            yield StreamEvent(provider=self._name, content=line + "\n")

        yield StreamEvent(provider=self._name, content="", is_complete=True)

    def _get_response_for_prompt(self, prompt: str) -> str:
        """Get the appropriate response for a prompt."""
        prompt_lower = prompt.lower()

        # Check for specific response patterns
        if "initial plan" in prompt_lower or "create a" in prompt_lower:
            return self._responses.get("plan", self.DEFAULT_RESPONSES["plan"])

        if "synthesize" in prompt_lower or "feedback" in prompt_lower:
            # Check if we should return converged response
            if "round 5" in prompt_lower or "final" in prompt_lower:
                return self._responses.get("converged", self.DEFAULT_RESPONSES["converged"])
            return self._responses.get("synthesis", self.DEFAULT_RESPONSES["synthesis"])

        if "review" in prompt_lower or "advisor" in prompt_lower:
            return self._responses.get("feedback", self.DEFAULT_RESPONSES["feedback"])

        # Check for custom responses by substring
        for key, value in self._responses.items():
            if key in prompt_lower:
                return value

        # Default to feedback response
        return self._responses.get("feedback", self.DEFAULT_RESPONSES["feedback"])


class MockAdapterFactory:
    """Factory for creating configured mock adapters."""

    @staticmethod
    def create_successful(name: str = "mock") -> MockAdapter:
        """Create a mock adapter that always succeeds."""
        return MockAdapter(name=name)

    @staticmethod
    def create_failing(name: str = "mock", error_type: ProviderErrorType = ProviderErrorType.UNKNOWN) -> MockAdapter:
        """Create a mock adapter that always fails."""
        adapter = MockAdapter(name=name)
        adapter.set_error(error_type)
        return adapter

    @staticmethod
    def create_timeout(name: str = "mock") -> MockAdapter:
        """Create a mock adapter that always times out."""
        adapter = MockAdapter(name=name)
        adapter.set_timeout(True)
        return adapter

    @staticmethod
    def create_flaky(name: str = "mock", fail_after: int = 2) -> MockAdapter:
        """Create a mock adapter that fails after N invocations."""
        adapter = MockAdapter(name=name)
        adapter.set_fail_after(fail_after)
        return adapter

    @staticmethod
    def create_converging(name: str = "mock", converge_at_round: int = 3) -> MockAdapter:
        """Create a mock adapter that converges at a specific round."""
        adapter = MockAdapter(name=name)

        def custom_response(prompt: str) -> str:
            if f"round {converge_at_round}" in prompt.lower():
                return MockAdapter.DEFAULT_RESPONSES["converged"]
            return MockAdapter.DEFAULT_RESPONSES["synthesis"]

        return adapter
