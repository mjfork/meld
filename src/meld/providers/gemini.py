"""Gemini CLI adapter."""

import asyncio

from meld.providers.base import ProviderAdapter


class GeminiAdapter(ProviderAdapter):
    """Adapter for the Gemini CLI."""

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def cli_command(self) -> str:
        return "gemini"

    def build_command(self, prompt: str) -> list[str]:
        """Build gemini CLI command."""
        return [
            self.cli_command,
            prompt,
        ]

    async def check_auth(self) -> bool:
        """Check if Gemini CLI is authenticated."""
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
