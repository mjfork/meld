"""OpenAI/Codex CLI adapter.

The Codex CLI uses the following flags:
- `exec` subcommand for execution
- `--sandbox read-only` for protection mode
- `--model` for model selection (default: gpt-5.2)

Error patterns:
- "invalid api key" / "unauthorized" / "authentication" -> AUTH_FAILED
- "rate limit" / "too many requests" / "429" -> RATE_LIMITED
- "connection" / "network" / "ECONNREFUSED" -> NETWORK_ERROR
"""

import asyncio
import re
import shutil

from meld.data_models import ProviderError, ProviderErrorType
from meld.providers.base import ProviderAdapter


class OpenAIAdapter(ProviderAdapter):
    """Adapter for the OpenAI CLI (codex or chatgpt).

    Builds commands with hardcoded flags for consistent behavior:
    - Read-only sandbox mode for protection
    - gpt-5.2 model by default
    - Uses `exec` subcommand for codex
    """

    # OpenAI-specific error patterns
    AUTH_PATTERNS = [
        re.compile(r"invalid.*api.?key", re.IGNORECASE),
        re.compile(r"unauthorized", re.IGNORECASE),
        re.compile(r"authentication.*failed", re.IGNORECASE),
        re.compile(r"OPENAI_API_KEY.*not set", re.IGNORECASE),
        re.compile(r"401", re.IGNORECASE),
    ]

    RATE_LIMIT_PATTERNS = [
        re.compile(r"rate.?limit", re.IGNORECASE),
        re.compile(r"too many requests", re.IGNORECASE),
        re.compile(r"429", re.IGNORECASE),
        re.compile(r"quota.*exceeded", re.IGNORECASE),
        re.compile(r"insufficient.*quota", re.IGNORECASE),
    ]

    NETWORK_PATTERNS = [
        re.compile(r"connection.*refused", re.IGNORECASE),
        re.compile(r"network.*error", re.IGNORECASE),
        re.compile(r"ECONNREFUSED", re.IGNORECASE),
        re.compile(r"timeout", re.IGNORECASE),
        re.compile(r"could not resolve", re.IGNORECASE),
    ]

    def __init__(self, timeout: int = 600, model: str = "gpt-5.2") -> None:
        """Initialize OpenAI adapter.

        Args:
            timeout: Command timeout in seconds.
            model: Model to use (default: gpt-5.2).
        """
        super().__init__(timeout=timeout)
        self.model = model
        self._cli_command: str | None = None

    @property
    def name(self) -> str:
        return "openai"

    @property
    def cli_command(self) -> str:
        """Get CLI command, preferring codex over chatgpt."""
        if self._cli_command is None:
            # Try codex first, fall back to chatgpt
            if shutil.which("codex"):
                self._cli_command = "codex"
            else:
                self._cli_command = "chatgpt"
        return self._cli_command

    def build_command(self, prompt: str) -> list[str]:
        """Build openai CLI command with proper flags.

        For codex:
            codex exec "{prompt}" --sandbox read-only --model gpt-5.2

        For chatgpt (fallback):
            chatgpt "{prompt}" --model gpt-5.2
        """
        cmd = self.cli_command
        if cmd == "codex":
            return [
                cmd,
                "exec",  # Execution subcommand
                prompt,
                "--sandbox",
                "read-only",  # Read-only protection
                "--model",
                self.model,
            ]
        # Fallback for chatgpt CLI
        return [
            cmd,
            prompt,
            "--model",
            self.model,
        ]

    async def check_auth(self) -> bool:
        """Check if OpenAI CLI is authenticated.

        Runs `codex --version` or `chatgpt --version` to verify CLI is installed.
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
        """Classify OpenAI-specific errors.

        Uses regex patterns to identify error types from stderr output.
        """
        # Check auth patterns first
        for pattern in self.AUTH_PATTERNS:
            if pattern.search(stderr):
                return ProviderError(
                    error_type=ProviderErrorType.AUTH_FAILED,
                    message="OpenAI CLI authentication failed",
                    provider=self.name,
                    details={"stderr": stderr},
                )

        # Check rate limit patterns
        for pattern in self.RATE_LIMIT_PATTERNS:
            if pattern.search(stderr):
                return ProviderError(
                    error_type=ProviderErrorType.RATE_LIMITED,
                    message="OpenAI API rate limited",
                    provider=self.name,
                    details={"stderr": stderr},
                    retryable=True,
                )

        # Check network patterns
        for pattern in self.NETWORK_PATTERNS:
            if pattern.search(stderr):
                return ProviderError(
                    error_type=ProviderErrorType.NETWORK_ERROR,
                    message="Network error connecting to OpenAI",
                    provider=self.name,
                    details={"stderr": stderr},
                    retryable=True,
                )

        # Fall back to base classification
        return super()._classify_error(stderr)
