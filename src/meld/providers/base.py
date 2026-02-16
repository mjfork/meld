"""Base provider adapter interface."""

import asyncio
import shutil
from abc import ABC, abstractmethod
from typing import AsyncIterator

from meld.data_models import AdvisorResult, ProviderError, ProviderErrorType, StreamEvent


class ProviderAdapter(ABC):
    """Abstract base class for provider adapters."""

    def __init__(self, timeout: int = 600) -> None:
        """Initialize adapter with timeout."""
        self.timeout = timeout

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the provider name."""
        ...

    @property
    @abstractmethod
    def cli_command(self) -> str:
        """Get the CLI command name."""
        ...

    def is_available(self) -> bool:
        """Check if the CLI is available on PATH."""
        return shutil.which(self.cli_command) is not None

    @abstractmethod
    def build_command(self, prompt: str) -> list[str]:
        """Build the CLI command with arguments."""
        ...

    @abstractmethod
    async def check_auth(self) -> bool:
        """Check if authentication is valid."""
        ...

    async def invoke(self, prompt: str) -> AdvisorResult:
        """Invoke the provider and return the result."""
        if not self.is_available():
            return AdvisorResult(
                provider=self.name,
                success=False,
                error=ProviderError(
                    error_type=ProviderErrorType.CLI_NOT_FOUND,
                    message=f"CLI '{self.cli_command}' not found on PATH",
                    provider=self.name,
                ),
            )

        cmd = self.build_command(prompt)
        try:
            import time

            start = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )

            duration = time.monotonic() - start

            if proc.returncode != 0:
                error = self._classify_error(stderr.decode())
                return AdvisorResult(
                    provider=self.name,
                    success=False,
                    error=error,
                    duration_seconds=duration,
                )

            return AdvisorResult(
                provider=self.name,
                success=True,
                feedback=self._parse_output(stdout.decode()),
                duration_seconds=duration,
            )

        except asyncio.TimeoutError:
            return AdvisorResult(
                provider=self.name,
                success=False,
                error=ProviderError(
                    error_type=ProviderErrorType.TIMEOUT,
                    message=f"Timeout after {self.timeout}s",
                    provider=self.name,
                    retryable=True,
                ),
            )
        except Exception as e:
            return AdvisorResult(
                provider=self.name,
                success=False,
                error=ProviderError(
                    error_type=ProviderErrorType.UNKNOWN,
                    message=str(e),
                    provider=self.name,
                ),
            )

    async def invoke_streaming(self, prompt: str) -> AsyncIterator[StreamEvent]:
        """Invoke the provider with streaming output."""
        if not self.is_available():
            yield StreamEvent(
                provider=self.name,
                content=f"Error: CLI '{self.cli_command}' not found",
                is_complete=True,
            )
            return

        cmd = self.build_command(prompt)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            assert proc.stdout is not None

            async for line in proc.stdout:
                yield StreamEvent(
                    provider=self.name,
                    content=line.decode(),
                )

            await proc.wait()
            yield StreamEvent(provider=self.name, content="", is_complete=True)

        except Exception as e:
            yield StreamEvent(
                provider=self.name,
                content=f"Error: {e}",
                is_complete=True,
            )

    def _classify_error(self, stderr: str) -> ProviderError:
        """Classify an error based on stderr output."""
        stderr_lower = stderr.lower()

        if "auth" in stderr_lower or "unauthorized" in stderr_lower or "api key" in stderr_lower:
            return ProviderError(
                error_type=ProviderErrorType.AUTH_FAILED,
                message="Authentication failed",
                provider=self.name,
                details={"stderr": stderr},
            )

        if "rate limit" in stderr_lower or "quota" in stderr_lower:
            return ProviderError(
                error_type=ProviderErrorType.RATE_LIMITED,
                message="Rate limited",
                provider=self.name,
                details={"stderr": stderr},
                retryable=True,
            )

        if "network" in stderr_lower or "connection" in stderr_lower:
            return ProviderError(
                error_type=ProviderErrorType.NETWORK_ERROR,
                message="Network error",
                provider=self.name,
                details={"stderr": stderr},
                retryable=True,
            )

        return ProviderError(
            error_type=ProviderErrorType.UNKNOWN,
            message=stderr[:500],
            provider=self.name,
            details={"stderr": stderr},
        )

    def _parse_output(self, stdout: str) -> str:
        """Parse and clean the CLI output."""
        return stdout.strip()
