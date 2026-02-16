"""Gemini CLI adapter.

The Gemini CLI uses the following flags:
- `-p` for prompt (non-interactive)
- `--sandbox` for read-only mode
- `-m` for model selection (default: gemini-2.5-pro)

Error patterns:
- "not authenticated" / "invalid credentials" / "unauthorized" -> AUTH_FAILED
- "rate limit" / "quota exceeded" / "resource exhausted" -> RATE_LIMITED
- "connection" / "network" / "UNAVAILABLE" -> NETWORK_ERROR
"""

import asyncio
import re

from meld.data_models import ProviderError, ProviderErrorType
from meld.providers.base import ProviderAdapter


class GeminiAdapter(ProviderAdapter):
    """Adapter for the Gemini CLI.

    Builds commands with hardcoded flags for consistent behavior:
    - Sandbox mode for read-only operation
    - gemini-2.5-pro model by default
    """

    # Gemini-specific error patterns
    AUTH_PATTERNS = [
        re.compile(r"not authenticated", re.IGNORECASE),
        re.compile(r"invalid.*credentials", re.IGNORECASE),
        re.compile(r"unauthorized", re.IGNORECASE),
        re.compile(r"UNAUTHENTICATED", re.IGNORECASE),
        re.compile(r"api.?key.*invalid", re.IGNORECASE),
        re.compile(r"permission.?denied", re.IGNORECASE),
    ]

    RATE_LIMIT_PATTERNS = [
        re.compile(r"rate.?limit", re.IGNORECASE),
        re.compile(r"quota.?exceeded", re.IGNORECASE),
        re.compile(r"resource.?exhausted", re.IGNORECASE),
        re.compile(r"RESOURCE_EXHAUSTED", re.IGNORECASE),
        re.compile(r"429", re.IGNORECASE),
    ]

    NETWORK_PATTERNS = [
        re.compile(r"connection.*refused", re.IGNORECASE),
        re.compile(r"network.*error", re.IGNORECASE),
        re.compile(r"UNAVAILABLE", re.IGNORECASE),
        re.compile(r"could not resolve", re.IGNORECASE),
        re.compile(r"deadline.?exceeded", re.IGNORECASE),
    ]

    def __init__(self, timeout: int = 600, model: str = "gemini-2.5-pro") -> None:
        """Initialize Gemini adapter.

        Args:
            timeout: Command timeout in seconds.
            model: Model to use (default: gemini-2.5-pro).
        """
        super().__init__(timeout=timeout)
        self.model = model

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def cli_command(self) -> str:
        return "gemini"

    def build_command(self, prompt: str) -> list[str]:
        """Build gemini CLI command with proper flags.

        Returns command like:
            gemini -p "{prompt}" -m gemini-2.5-pro --sandbox
        """
        return [
            self.cli_command,
            "-p",  # Prompt mode
            prompt,
            "-m",  # Model selection
            self.model,
            "--sandbox",  # Read-only mode
        ]

    async def check_auth(self) -> bool:
        """Check if Gemini CLI is authenticated.

        Runs `gemini --version` to verify CLI is installed and working.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                self.cli_command,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            return proc.returncode == 0
        except Exception:
            return False

    def _classify_error(self, stderr: str) -> ProviderError:
        """Classify Gemini-specific errors.

        Uses regex patterns to identify error types from stderr output.
        """
        # Check auth patterns first
        for pattern in self.AUTH_PATTERNS:
            if pattern.search(stderr):
                return ProviderError(
                    error_type=ProviderErrorType.AUTH_FAILED,
                    message="Gemini CLI authentication failed",
                    provider=self.name,
                    details={"stderr": stderr},
                )

        # Check rate limit patterns
        for pattern in self.RATE_LIMIT_PATTERNS:
            if pattern.search(stderr):
                return ProviderError(
                    error_type=ProviderErrorType.RATE_LIMITED,
                    message="Gemini API rate limited",
                    provider=self.name,
                    details={"stderr": stderr},
                    retryable=True,
                )

        # Check network patterns
        for pattern in self.NETWORK_PATTERNS:
            if pattern.search(stderr):
                return ProviderError(
                    error_type=ProviderErrorType.NETWORK_ERROR,
                    message="Network error connecting to Gemini",
                    provider=self.name,
                    details={"stderr": stderr},
                    retryable=True,
                )

        # Fall back to base classification
        return super()._classify_error(stderr)
