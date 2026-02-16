"""Claude CLI adapter."""

import asyncio

from meld.providers.base import ProviderAdapter


class ClaudeAdapter(ProviderAdapter):
    """Adapter for the Claude CLI."""

    @property
    def name(self) -> str:
        return "claude"

    @property
    def cli_command(self) -> str:
        return "claude"

    def build_command(self, prompt: str) -> list[str]:
        """Build claude CLI command."""
        return [
            self.cli_command,
            "-p",  # Print mode (non-interactive)
            prompt,
        ]

    async def check_auth(self) -> bool:
        """Check if Claude CLI is authenticated."""
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
