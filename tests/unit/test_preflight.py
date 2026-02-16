"""Tests for preflight checks and doctor command."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meld.preflight import (
    AUTH_INSTRUCTIONS,
    INSTALL_INSTRUCTIONS,
    PreflightResult,
    ProviderCheckResult,
    check_cli_exists,
    get_cli_path,
    get_cli_version,
    run_doctor,
    run_preflight,
    run_preflight_checks,
)


class TestCheckCliExists:
    """Tests for check_cli_exists function."""

    def test_returns_true_for_existing_command(self) -> None:
        """Returns True for commands that exist on PATH."""
        # 'python3' or 'sh' should exist
        with patch("meld.preflight.shutil.which", return_value="/usr/bin/python3"):
            assert check_cli_exists("python3") is True

    def test_returns_false_for_missing_command(self) -> None:
        """Returns False for commands not on PATH."""
        with patch("meld.preflight.shutil.which", return_value=None):
            assert check_cli_exists("nonexistent_command_xyz") is False


class TestGetCliPath:
    """Tests for get_cli_path function."""

    def test_returns_path_for_existing_command(self) -> None:
        """Returns full path for existing commands."""
        with patch("meld.preflight.shutil.which", return_value="/usr/bin/python3"):
            assert get_cli_path("python3") == "/usr/bin/python3"

    def test_returns_empty_for_missing_command(self) -> None:
        """Returns empty string for missing commands."""
        with patch("meld.preflight.shutil.which", return_value=None):
            assert get_cli_path("nonexistent") == ""


class TestGetCliVersion:
    """Tests for get_cli_version function."""

    @pytest.mark.asyncio
    async def test_returns_version_string(self) -> None:
        """Returns version string from CLI output."""
        mock_adapter = MagicMock()
        mock_adapter.is_available.return_value = True
        mock_adapter.cli_command = "test"

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"1.2.3\n", b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            version = await get_cli_version(mock_adapter)
            assert version == "1.2.3"

    @pytest.mark.asyncio
    async def test_returns_empty_when_cli_not_available(self) -> None:
        """Returns empty string when CLI is not available."""
        mock_adapter = MagicMock()
        mock_adapter.is_available.return_value = False

        version = await get_cli_version(mock_adapter)
        assert version == ""

    @pytest.mark.asyncio
    async def test_handles_timeout_gracefully(self) -> None:
        """Handles timeout gracefully by returning empty string."""
        mock_adapter = MagicMock()
        mock_adapter.is_available.return_value = True
        mock_adapter.cli_command = "test"

        with patch(
            "asyncio.create_subprocess_exec", side_effect=asyncio.TimeoutError()
        ):
            version = await get_cli_version(mock_adapter)
            assert version == ""


class TestPreflightResult:
    """Tests for PreflightResult dataclass."""

    def test_creates_with_required_fields(self) -> None:
        """Creates result with required fields."""
        result = PreflightResult(passed=True)
        assert result.passed is True
        assert result.errors == []
        assert result.warnings == []
        assert result.available_advisors == []

    def test_creates_with_all_fields(self) -> None:
        """Creates result with all fields populated."""
        result = PreflightResult(
            passed=False,
            errors=["error1", "error2"],
            warnings=["warning1"],
            available_advisors=["claude", "gemini"],
        )
        assert result.passed is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1
        assert len(result.available_advisors) == 2


class TestRunPreflight:
    """Tests for run_preflight function."""

    @pytest.mark.asyncio
    async def test_returns_passed_when_skip_is_true(self) -> None:
        """Returns passed result when skip=True."""
        result = await run_preflight(skip=True)
        assert result.passed is True
        assert result.available_advisors == ["claude", "gemini", "openai"]
        assert result.errors == []
        assert result.warnings == []

    @pytest.mark.asyncio
    async def test_passes_with_all_clis_available(self) -> None:
        """Passes when all CLIs are available."""
        mock_results = [
            ProviderCheckResult(provider="claude", cli_found=True, auth_valid=True),
            ProviderCheckResult(provider="gemini", cli_found=True, auth_valid=True),
            ProviderCheckResult(provider="openai", cli_found=True, auth_valid=True),
        ]
        with patch(
            "meld.preflight.run_preflight_checks", return_value=mock_results
        ):
            result = await run_preflight(skip=False)
            assert result.passed is True
            assert len(result.available_advisors) == 3
            assert result.errors == []

    @pytest.mark.asyncio
    async def test_warns_but_passes_with_one_cli_missing(self) -> None:
        """Warns but passes when only one CLI is missing."""
        mock_results = [
            ProviderCheckResult(provider="claude", cli_found=True, auth_valid=True),
            ProviderCheckResult(provider="gemini", cli_found=True, auth_valid=True),
            ProviderCheckResult(provider="openai", cli_found=False),
        ]
        with patch(
            "meld.preflight.run_preflight_checks", return_value=mock_results
        ):
            result = await run_preflight(skip=False)
            assert result.passed is True
            assert len(result.available_advisors) == 2
            # Missing CLI should be a warning, not error
            assert result.errors == []
            assert len(result.warnings) > 0
            assert "openai" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_fails_when_two_or_more_clis_missing(self) -> None:
        """Fails when two or more CLIs are missing."""
        mock_results = [
            ProviderCheckResult(provider="claude", cli_found=True, auth_valid=True),
            ProviderCheckResult(provider="gemini", cli_found=False),
            ProviderCheckResult(provider="openai", cli_found=False),
        ]
        with patch(
            "meld.preflight.run_preflight_checks", return_value=mock_results
        ):
            result = await run_preflight(skip=False)
            assert result.passed is False
            assert len(result.available_advisors) == 1
            assert len(result.errors) == 2

    @pytest.mark.asyncio
    async def test_includes_install_instructions_in_errors(self) -> None:
        """Includes install instructions in error messages."""
        mock_results = [
            ProviderCheckResult(provider="claude", cli_found=False),
            ProviderCheckResult(provider="gemini", cli_found=False),
            ProviderCheckResult(provider="openai", cli_found=False),
        ]
        with patch(
            "meld.preflight.run_preflight_checks", return_value=mock_results
        ):
            result = await run_preflight(skip=False)
            assert result.passed is False
            # Check install instructions are included
            for error in result.errors:
                assert "Install:" in error

    @pytest.mark.asyncio
    async def test_warns_about_auth_issues(self) -> None:
        """Warns about auth issues even when CLI is available."""
        mock_results = [
            ProviderCheckResult(
                provider="claude", cli_found=True, auth_valid=False, auth_status="not authenticated"
            ),
            ProviderCheckResult(provider="gemini", cli_found=True, auth_valid=True),
            ProviderCheckResult(provider="openai", cli_found=True, auth_valid=True),
        ]
        with patch(
            "meld.preflight.run_preflight_checks", return_value=mock_results
        ):
            result = await run_preflight(skip=False)
            assert result.passed is True
            assert "claude" in str(result.warnings)


class TestRunDoctor:
    """Tests for run_doctor function."""

    def test_returns_zero_when_all_providers_ready(self) -> None:
        """Returns 0 when all providers are ready."""
        mock_results = [
            ProviderCheckResult(
                provider="claude",
                cli_found=True,
                cli_path="/usr/bin/claude",
                version="1.0.0",
                auth_valid=True,
            ),
            ProviderCheckResult(
                provider="gemini",
                cli_found=True,
                cli_path="/usr/bin/gemini",
                version="2.0.0",
                auth_valid=True,
            ),
            ProviderCheckResult(
                provider="openai",
                cli_found=True,
                cli_path="/usr/bin/codex",
                version="3.0.0",
                auth_valid=True,
            ),
        ]
        with patch("meld.preflight.asyncio.run", return_value=mock_results):
            exit_code = run_doctor()
            assert exit_code == 0

    def test_returns_zero_with_at_least_one_provider(self) -> None:
        """Returns 0 when at least one provider is available."""
        mock_results = [
            ProviderCheckResult(
                provider="claude",
                cli_found=True,
                cli_path="/usr/bin/claude",
                version="1.0.0",
                auth_valid=True,
            ),
            ProviderCheckResult(provider="gemini", cli_found=False),
            ProviderCheckResult(provider="openai", cli_found=False),
        ]
        with patch("meld.preflight.asyncio.run", return_value=mock_results):
            exit_code = run_doctor()
            assert exit_code == 0

    def test_returns_two_when_no_providers_available(self) -> None:
        """Returns 2 when no providers are available."""
        mock_results = [
            ProviderCheckResult(provider="claude", cli_found=False),
            ProviderCheckResult(provider="gemini", cli_found=False),
            ProviderCheckResult(provider="openai", cli_found=False),
        ]
        with patch("meld.preflight.asyncio.run", return_value=mock_results):
            exit_code = run_doctor()
            assert exit_code == 2

    def test_shows_install_instructions(self, capsys: pytest.CaptureFixture) -> None:
        """Shows install instructions for missing CLIs."""
        mock_results = [
            ProviderCheckResult(provider="claude", cli_found=False),
            ProviderCheckResult(provider="gemini", cli_found=False),
            ProviderCheckResult(provider="openai", cli_found=False),
        ]
        with patch("meld.preflight.asyncio.run", return_value=mock_results):
            run_doctor()
            captured = capsys.readouterr()
            assert "Install:" in captured.out
            assert INSTALL_INSTRUCTIONS["claude"] in captured.out

    def test_shows_version_for_installed_clis(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Shows version information for installed CLIs."""
        mock_results = [
            ProviderCheckResult(
                provider="claude",
                cli_found=True,
                cli_path="/usr/bin/claude",
                version="1.5.0",
                auth_valid=True,
            ),
            ProviderCheckResult(provider="gemini", cli_found=False),
            ProviderCheckResult(provider="openai", cli_found=False),
        ]
        with patch("meld.preflight.asyncio.run", return_value=mock_results):
            run_doctor()
            captured = capsys.readouterr()
            assert "Version: 1.5.0" in captured.out

    def test_shows_auth_status(self, capsys: pytest.CaptureFixture) -> None:
        """Shows auth status for installed CLIs."""
        mock_results = [
            ProviderCheckResult(
                provider="claude",
                cli_found=True,
                cli_path="/usr/bin/claude",
                version="1.0.0",
                auth_valid=True,
            ),
            ProviderCheckResult(
                provider="gemini",
                cli_found=True,
                cli_path="/usr/bin/gemini",
                version="2.0.0",
                auth_valid=False,
                auth_status="not authenticated",
            ),
            ProviderCheckResult(provider="openai", cli_found=False),
        ]
        with patch("meld.preflight.asyncio.run", return_value=mock_results):
            run_doctor()
            captured = capsys.readouterr()
            assert "Authenticated" in captured.out
            assert "not authenticated" in captured.out

    def test_suggests_auth_fix(self, capsys: pytest.CaptureFixture) -> None:
        """Suggests how to fix auth issues."""
        mock_results = [
            ProviderCheckResult(
                provider="claude",
                cli_found=True,
                cli_path="/usr/bin/claude",
                version="1.0.0",
                auth_valid=False,
                auth_status="not authenticated",
            ),
            ProviderCheckResult(provider="gemini", cli_found=False),
            ProviderCheckResult(provider="openai", cli_found=False),
        ]
        with patch("meld.preflight.asyncio.run", return_value=mock_results):
            run_doctor()
            captured = capsys.readouterr()
            assert AUTH_INSTRUCTIONS["claude"] in captured.out


class TestInstallInstructions:
    """Tests for install instructions constants."""

    def test_has_instruction_for_each_provider(self) -> None:
        """Has install instruction for each provider."""
        assert "claude" in INSTALL_INSTRUCTIONS
        assert "gemini" in INSTALL_INSTRUCTIONS
        assert "openai" in INSTALL_INSTRUCTIONS


class TestAuthInstructions:
    """Tests for auth instructions constants."""

    def test_has_instruction_for_each_provider(self) -> None:
        """Has auth instruction for each provider."""
        assert "claude" in AUTH_INSTRUCTIONS
        assert "gemini" in AUTH_INSTRUCTIONS
        assert "openai" in AUTH_INSTRUCTIONS
