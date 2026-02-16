"""OpenAI/Codex CLI adapter."""

import asyncio
import shutil

from meld.providers.base import ProviderAdapter


class OpenAIAdapter(ProviderAdapter):
    """Adapter for the OpenAI CLI (codex or chatgpt)."""

    @property
    def name(self) -> str:
        return "openai"

    @property
    def cli_command(self) -> str:
        # Try codex first, fall back to chatgpt
        if shutil.which("codex"):
            return "codex"
        return "chatgpt"

    def build_command(self, prompt: str) -> list[str]:
        """Build openai CLI command."""
        return [
            self.cli_command,
            prompt,
        ]

    async def check_auth(self) -> bool:
        """Check if OpenAI CLI is authenticated."""
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
