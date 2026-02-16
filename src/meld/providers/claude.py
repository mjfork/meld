"""Claude CLI adapter.

The Claude CLI uses the following flags:
- `-p` for prompt mode (non-interactive)
- `--permission-mode plan` for read-only mode (no file writes)
- `--output-format text` for plain text output
- `--model` for model selection (default: opus)

Error patterns:
- "not logged in" / "authentication required" / "unauthorized" -> AUTH_FAILED
- "rate limit" / "quota exceeded" / "too many requests" -> RATE_LIMITED
- "connection refused" / "network unreachable" / "DNS" -> NETWORK_ERROR
"""

import asyncio
import re

from meld.data_models import ProviderError, ProviderErrorType
from meld.providers.base import ProviderAdapter


class ClaudeAdapter(ProviderAdapter):
    """Adapter for the Claude CLI.

    Builds commands with hardcoded flags for consistent behavior:
    - Read-only mode (--permission-mode plan)
    - Plain text output (--output-format text)
    - Opus model by default
    """

    # Claude-specific error patterns
    AUTH_PATTERNS = [
        re.compile(r"not logged in", re.IGNORECASE),
        re.compile(r"authentication required", re.IGNORECASE),
        re.compile(r"unauthorized", re.IGNORECASE),
        re.compile(r"invalid.*api.?key", re.IGNORECASE),
        re.compile(r"please run.*auth", re.IGNORECASE),
    ]

    RATE_LIMIT_PATTERNS = [
        re.compile(r"rate.?limit", re.IGNORECASE),
        re.compile(r"quota.?exceeded", re.IGNORECASE),
        re.compile(r"too many requests", re.IGNORECASE),
        re.compile(r"429", re.IGNORECASE),
    ]

    NETWORK_PATTERNS = [
        re.compile(r"connection.?refused", re.IGNORECASE),
        re.compile(r"network.?unreachable", re.IGNORECASE),
        re.compile(r"dns.*failed", re.IGNORECASE),
        re.compile(r"could not resolve", re.IGNORECASE),
        re.compile(r"ECONNREFUSED", re.IGNORECASE),
    ]

    def __init__(self, timeout: int = 600, model: str = "opus") -> None:
        """Initialize Claude adapter.

        Args:
            timeout: Command timeout in seconds.
            model: Model to use (default: opus).
        """
        super().__init__(timeout=timeout)
        self.model = model

    @property
    def name(self) -> str:
        return "claude"

    @property
    def cli_command(self) -> str:
        return "claude"

    def build_command(self, prompt: str) -> list[str]:
        """Build claude CLI command with proper flags.

        Returns command like:
            claude -p "{prompt}" --permission-mode plan --model opus --output-format text
        """
        return [
            self.cli_command,
            "-p",  # Prompt mode (non-interactive)
            prompt,
            "--permission-mode",
            "plan",  # Read-only mode
            "--model",
            self.model,
            "--output-format",
            "text",  # Plain text output
        ]

    async def check_auth(self) -> bool:
        """Check if Claude CLI is authenticated.

        Runs `claude --version` to verify CLI is installed and working.
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
        """Classify Claude-specific errors.

        Uses regex patterns to identify error types from stderr output.
        """
        # Check auth patterns first
        for pattern in self.AUTH_PATTERNS:
            if pattern.search(stderr):
                return ProviderError(
                    error_type=ProviderErrorType.AUTH_FAILED,
                    message="Claude CLI authentication failed",
                    provider=self.name,
                    details={"stderr": stderr},
                )

        # Check rate limit patterns
        for pattern in self.RATE_LIMIT_PATTERNS:
            if pattern.search(stderr):
                return ProviderError(
                    error_type=ProviderErrorType.RATE_LIMITED,
                    message="Claude API rate limited",
                    provider=self.name,
                    details={"stderr": stderr},
                    retryable=True,
                )

        # Check network patterns
        for pattern in self.NETWORK_PATTERNS:
            if pattern.search(stderr):
                return ProviderError(
                    error_type=ProviderErrorType.NETWORK_ERROR,
                    message="Network error connecting to Claude",
                    provider=self.name,
                    details={"stderr": stderr},
                    retryable=True,
                )

        # Fall back to base classification
        return super()._classify_error(stderr)
