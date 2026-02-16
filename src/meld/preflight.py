"""Preflight checks and diagnostics."""

import asyncio
import shutil
from dataclasses import dataclass, field

from meld.providers import ClaudeAdapter, GeminiAdapter, OpenAIAdapter, ProviderAdapter

# Install instructions per provider
INSTALL_INSTRUCTIONS: dict[str, str] = {
    "claude": "npm install -g @anthropic-ai/claude-code",
    "gemini": "npm install -g @google/gemini-cli",
    "openai": "npm install -g @openai/codex",
}

# Auth fix instructions per provider
AUTH_INSTRUCTIONS: dict[str, str] = {
    "claude": "claude auth login",
    "gemini": "gemini auth login",
    "openai": "codex auth login",
}


@dataclass
class ProviderCheckResult:
    """Result of checking a single provider."""

    provider: str
    cli_found: bool
    cli_path: str = ""
    version: str = ""
    auth_valid: bool = False
    auth_status: str = "unknown"
    error: str = ""


@dataclass
class PreflightResult:
    """Result of preflight checks.

    Attributes:
        passed: Whether preflight passed (at least 1 CLI available).
        errors: List of error messages.
        warnings: List of warning messages.
        available_advisors: List of advisor names that are available.
    """

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    available_advisors: list[str] = field(default_factory=list)


def check_cli_exists(command: str) -> bool:
    """Check if a CLI command exists on PATH."""
    return shutil.which(command) is not None


def get_cli_path(command: str) -> str:
    """Get the full path to a CLI command."""
    path = shutil.which(command)
    return path if path else ""


async def get_cli_version(adapter: ProviderAdapter) -> str:
    """Get the version of a CLI tool."""
    if not adapter.is_available():
        return ""

    try:
        proc = await asyncio.create_subprocess_exec(
            adapter.cli_command,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            # Extract version from output (usually first line or number)
            output = stdout.decode().strip()
            # Return first line which typically contains version
            return output.split("\n")[0].strip()
        return ""
    except Exception:
        return ""


async def check_provider(adapter: ProviderAdapter) -> ProviderCheckResult:
    """Run preflight checks for a provider."""
    result = ProviderCheckResult(
        provider=adapter.name,
        cli_found=adapter.is_available(),
    )

    if not result.cli_found:
        result.error = f"CLI '{adapter.cli_command}' not found on PATH"
        return result

    result.cli_path = get_cli_path(adapter.cli_command)
    result.version = await get_cli_version(adapter)
    result.auth_valid = await adapter.check_auth()

    if result.auth_valid:
        result.auth_status = "authenticated"
    else:
        result.auth_status = "not authenticated"
        result.error = f"Authentication check failed for {adapter.name}"

    return result


async def run_preflight_checks() -> list[ProviderCheckResult]:
    """Run preflight checks for all providers.

    Returns detailed results for each provider.
    """
    adapters: list[ProviderAdapter] = [
        ClaudeAdapter(),
        GeminiAdapter(),
        OpenAIAdapter(),
    ]

    results = await asyncio.gather(*[check_provider(a) for a in adapters])
    return list(results)


async def run_preflight(skip: bool = False) -> PreflightResult:
    """Run preflight checks.

    Args:
        skip: If True, skip all checks and return passed.

    Returns:
        PreflightResult with status and issues.
    """
    if skip:
        return PreflightResult(
            passed=True,
            available_advisors=["claude", "gemini", "openai"],
        )

    check_results = await run_preflight_checks()

    errors: list[str] = []
    warnings: list[str] = []
    available: list[str] = []

    for result in check_results:
        if result.cli_found:
            available.append(result.provider)
            if not result.auth_valid:
                warnings.append(
                    f"{result.provider}: {result.auth_status}. "
                    f"Run: {AUTH_INSTRUCTIONS.get(result.provider, f'{result.provider} auth login')}"
                )
        else:
            install_cmd = INSTALL_INSTRUCTIONS.get(
                result.provider, f"See {result.provider} documentation"
            )
            errors.append(f"{result.provider}: CLI not found. Install: {install_cmd}")

    # Determine if we pass based on available advisors
    # 1 missing: warn but continue
    # 2+ missing: error and stop
    missing_count = 3 - len(available)

    if missing_count >= 2:
        passed = False
    else:
        passed = True
        # Convert CLI errors to warnings if we have enough advisors
        if missing_count == 1:
            warnings.extend(errors)
            errors = []

    return PreflightResult(
        passed=passed,
        errors=errors,
        warnings=warnings,
        available_advisors=available,
    )


def run_doctor() -> int:
    """Run comprehensive diagnostics and print results.

    Always runs to completion, showing all issues.

    Returns:
        0 if all checks pass, 2 if critical issues exist.
    """
    print("Meld Doctor - System Check")
    print("=" * 26)
    print()

    results = asyncio.run(run_preflight_checks())

    available_count = 0

    for result in results:
        print(result.provider)

        if not result.cli_found:
            print("  ✗ Not installed")
            install_cmd = INSTALL_INSTRUCTIONS.get(
                result.provider, f"See {result.provider} documentation"
            )
            print(f"  → Install: {install_cmd}")
        else:
            available_count += 1
            print(f"  ✓ Installed: {result.cli_path}")

            if result.version:
                print(f"  ✓ Version: {result.version}")
            else:
                print("  ⚠ Version: unable to detect")

            if result.auth_valid:
                print("  ✓ Authenticated")
            else:
                auth_cmd = AUTH_INSTRUCTIONS.get(
                    result.provider, f"{result.provider} auth login"
                )
                print(f"  ⚠ Authentication: {result.auth_status}")
                print(f"  → Fix: {auth_cmd}")

        print()

    # Summary
    print(f"Summary: {available_count}/3 advisors available")

    if available_count == 3:
        print("All providers ready!")
        return 0
    elif available_count >= 1:
        print("Meld can run with reduced advisor pool.")
        return 0
    else:
        print("No advisors available. Install at least one CLI to use Meld.")
        return 2


# Keep backward compatibility for existing code
PrefightResult = ProviderCheckResult
