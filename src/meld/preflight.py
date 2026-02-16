"""Preflight checks and diagnostics."""

import asyncio
import shutil
from dataclasses import dataclass

from meld.providers import ClaudeAdapter, GeminiAdapter, OpenAIAdapter, ProviderAdapter


@dataclass
class PrefightResult:
    """Result of a preflight check."""

    provider: str
    cli_found: bool
    auth_valid: bool
    version: str = ""
    error: str = ""


def check_cli_exists(command: str) -> bool:
    """Check if a CLI command exists on PATH."""
    return shutil.which(command) is not None


async def check_provider(adapter: ProviderAdapter) -> PrefightResult:
    """Run preflight checks for a provider."""
    result = PrefightResult(
        provider=adapter.name,
        cli_found=adapter.is_available(),
        auth_valid=False,
    )

    if not result.cli_found:
        result.error = f"CLI '{adapter.cli_command}' not found on PATH"
        return result

    result.auth_valid = await adapter.check_auth()
    if not result.auth_valid:
        result.error = f"Authentication check failed for {adapter.name}"

    return result


async def run_preflight() -> list[PrefightResult]:
    """Run preflight checks for all providers."""
    adapters: list[ProviderAdapter] = [
        ClaudeAdapter(),
        GeminiAdapter(),
        OpenAIAdapter(),
    ]

    results = await asyncio.gather(*[check_provider(a) for a in adapters])
    return list(results)


def run_doctor() -> int:
    """Run the doctor command to diagnose issues."""
    print("Meld Doctor - Checking environment...")
    print()

    results = asyncio.run(run_preflight())

    all_ok = True
    for result in results:
        status = "✓" if result.cli_found and result.auth_valid else "✗"
        print(f"{status} {result.provider}")

        if not result.cli_found:
            print(f"  └─ CLI not found: {result.error}")
            print(f"     Install: See {result.provider} documentation")
            all_ok = False
        elif not result.auth_valid:
            print(f"  └─ Auth failed: {result.error}")
            print(f"     Fix: Run '{result.provider} auth login' or configure API key")
            all_ok = False
        else:
            print("  └─ Ready")

        print()

    if all_ok:
        print("All providers ready!")
        return 0
    else:
        print("Some providers need attention.")
        print("Meld can still run with available providers (graceful degradation).")
        return 1
