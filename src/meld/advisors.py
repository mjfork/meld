"""Advisor pool for parallel feedback collection."""

import asyncio
from collections.abc import Callable

from meld.data_models import AdvisorResult, ProviderErrorType
from meld.prompts import ADVISOR_PROMPT
from meld.providers import ClaudeAdapter, GeminiAdapter, OpenAIAdapter, ProviderAdapter


class AdvisorPool:
    """Pool of advisors for parallel feedback collection."""

    # Retry configuration by error type
    RETRY_CONFIG: dict[ProviderErrorType, dict[str, int | float]] = {
        ProviderErrorType.TIMEOUT: {"max_retries": 1, "backoff": 0},
        ProviderErrorType.RATE_LIMITED: {"max_retries": 3, "backoff": 1.0},
        ProviderErrorType.NETWORK_ERROR: {"max_retries": 3, "backoff": 3.0},
    }

    def __init__(
        self,
        timeout: int = 600,
        on_status_change: Callable[[str, str], None] | None = None,
    ) -> None:
        """Initialize the advisor pool."""
        self._timeout = timeout
        self._on_status_change = on_status_change

        self._adapters: list[ProviderAdapter] = [
            ClaudeAdapter(timeout=timeout),
            GeminiAdapter(timeout=timeout),
            OpenAIAdapter(timeout=timeout),
        ]

    @property
    def advisor_names(self) -> list[str]:
        """Get list of advisor names."""
        return [a.name for a in self._adapters]

    async def collect_feedback(
        self,
        plan: str,
        task: str,
        prd_context: str | None = None,
        round_number: int = 1,
    ) -> list[AdvisorResult]:
        """Collect feedback from all advisors in parallel."""
        prompt = ADVISOR_PROMPT.format(
            task=task,
            plan=plan,
            prd_context=prd_context or "No additional context.",
        )

        tasks = [
            self._invoke_with_retry(adapter, prompt, round_number)
            for adapter in self._adapters
        ]

        results: list[AdvisorResult | BaseException] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        # Convert exceptions to failed results
        processed: list[AdvisorResult] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                processed.append(
                    AdvisorResult(
                        provider=self._adapters[i].name,
                        success=False,
                        round_number=round_number,
                    )
                )
            else:
                processed.append(result)

        return processed

    async def _invoke_with_retry(
        self,
        adapter: ProviderAdapter,
        prompt: str,
        round_number: int,
    ) -> AdvisorResult:
        """Invoke an adapter with retry logic."""
        self._notify_status(adapter.name, "running")

        result = await adapter.invoke(prompt)
        result.round_number = round_number

        if result.success:
            self._notify_status(adapter.name, "complete")
            return result

        # Check if error is retryable
        if result.error and result.error.error_type in self.RETRY_CONFIG:
            config = self.RETRY_CONFIG[result.error.error_type]
            max_retries = int(config["max_retries"])
            backoff = float(config["backoff"])

            for attempt in range(max_retries):
                self._notify_status(adapter.name, "retrying")
                await asyncio.sleep(backoff * (attempt + 1))

                result = await adapter.invoke(prompt)
                result.round_number = round_number

                if result.success:
                    self._notify_status(adapter.name, "complete")
                    return result

        self._notify_status(adapter.name, "failed")
        return result

    def _notify_status(self, provider: str, status: str) -> None:
        """Notify status change if callback is registered."""
        if self._on_status_change:
            self._on_status_change(provider, status)

    def get_participating_advisors(self, results: list[AdvisorResult]) -> list[str]:
        """Get list of advisors that successfully participated."""
        return [r.provider for r in results if r.success]
