"""Shared pytest fixtures for meld tests."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meld.data_models import (
    AdvisorResult,
    ConvergenceAssessment,
    ConvergenceStatus,
    SessionMetadata,
    StreamEvent,
)


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def sample_task() -> str:
    """Sample task description for testing."""
    return "Add user authentication with OAuth2 support"


@pytest.fixture
def sample_plan() -> str:
    """Sample plan content for testing."""
    return """## Overview
Implement OAuth2 authentication for user login.

## Steps
1. Set up OAuth2 provider configuration
2. Create authentication middleware
3. Implement login/logout endpoints
4. Add session management

## Considerations
- Security best practices
- Token refresh handling

## Risks
- Provider API changes
- Token expiration edge cases
"""


@pytest.fixture
def sample_prd() -> str:
    """Sample PRD content for testing."""
    return """# Authentication Requirements

## Goals
- Secure user authentication
- Support multiple OAuth providers
- Remember me functionality
"""


@pytest.fixture
def sample_feedback() -> str:
    """Sample advisor feedback for testing."""
    return """## Improvements
- Consider adding rate limiting to prevent brute force attacks
- Add logout from all devices functionality

## Concerns
- Token storage security in browser
- CORS configuration for OAuth callbacks

## Additions
- Add password reset flow
- Include audit logging for auth events

## Rationale
These changes enhance security and user experience.
"""


# ============================================================================
# Session Fixtures
# ============================================================================


@pytest.fixture
def temp_run_dir(tmp_path: Path) -> Path:
    """Create a temporary run directory."""
    run_dir = tmp_path / ".meld" / "runs"
    run_dir.mkdir(parents=True)
    return run_dir


@pytest.fixture
def sample_session_metadata() -> SessionMetadata:
    """Create sample session metadata."""
    return SessionMetadata(
        session_id="20260116-120000-abcd1234",
        task="Add user authentication",
        max_rounds=5,
        advisors_participated=["claude", "gemini"],
    )


# ============================================================================
# Mock Adapter Fixtures
# ============================================================================


@pytest.fixture
def mock_adapter():
    """Create a mock provider adapter."""
    from tests.mocks.mock_adapter import MockAdapter

    return MockAdapter()


@pytest.fixture
def mock_adapter_with_responses():
    """Factory fixture for creating mock adapters with specific responses."""
    from tests.mocks.mock_adapter import MockAdapter

    def _create(responses: dict[str, str] | None = None, fail_after: int | None = None):
        adapter = MockAdapter()
        if responses:
            adapter.set_responses(responses)
        if fail_after is not None:
            adapter.set_fail_after(fail_after)
        return adapter

    return _create


# ============================================================================
# Data Model Fixtures
# ============================================================================


@pytest.fixture
def successful_advisor_result(sample_feedback: str) -> AdvisorResult:
    """Create a successful advisor result."""
    return AdvisorResult(
        provider="mock",
        success=True,
        feedback=sample_feedback,
        duration_seconds=2.5,
        round_number=1,
    )


@pytest.fixture
def failed_advisor_result() -> AdvisorResult:
    """Create a failed advisor result."""
    from meld.data_models import ProviderError, ProviderErrorType

    return AdvisorResult(
        provider="mock",
        success=False,
        error=ProviderError(
            error_type=ProviderErrorType.TIMEOUT,
            message="Timeout after 600s",
            provider="mock",
            retryable=True,
        ),
        round_number=1,
    )


@pytest.fixture
def converged_assessment() -> ConvergenceAssessment:
    """Create a converged assessment."""
    return ConvergenceAssessment(
        status=ConvergenceStatus.CONVERGED,
        changes_made=0,
        open_items=0,
        diff_ratio=0.02,
        rationale="No substantive changes needed",
    )


@pytest.fixture
def continuing_assessment() -> ConvergenceAssessment:
    """Create a continuing assessment."""
    return ConvergenceAssessment(
        status=ConvergenceStatus.CONTINUING,
        changes_made=3,
        open_items=2,
        diff_ratio=0.15,
        rationale="Still improving plan",
    )


# ============================================================================
# Async Fixtures
# ============================================================================


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Mock Provider Fixtures
# ============================================================================


@pytest.fixture
def mock_claude_adapter():
    """Mock the Claude adapter for testing without real CLI."""
    with patch("meld.providers.claude.ClaudeAdapter") as mock:
        instance = mock.return_value
        instance.name = "claude"
        instance.cli_command = "claude"
        instance.is_available.return_value = True
        instance.check_auth = AsyncMock(return_value=True)
        instance.invoke = AsyncMock(
            return_value=AdvisorResult(
                provider="claude",
                success=True,
                feedback="Mock Claude feedback",
                duration_seconds=1.0,
            )
        )
        yield instance


@pytest.fixture
def mock_all_adapters(sample_feedback: str):
    """Mock all provider adapters."""
    adapters = {}

    for name in ["claude", "gemini", "openai"]:
        mock = MagicMock()
        mock.name = name
        mock.cli_command = name if name != "openai" else "codex"
        mock.is_available.return_value = True
        mock.check_auth = AsyncMock(return_value=True)
        mock.invoke = AsyncMock(
            return_value=AdvisorResult(
                provider=name,
                success=True,
                feedback=f"Mock {name} feedback: {sample_feedback}",
                duration_seconds=1.0,
            )
        )
        adapters[name] = mock

    return adapters


# ============================================================================
# Logging Fixtures
# ============================================================================


@pytest.fixture
def capture_logs(tmp_path: Path) -> Generator[Path, None, None]:
    """Capture test logs to a file."""
    log_file = tmp_path / "test.log"

    import logging

    handler = logging.FileHandler(log_file)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)

    logger = logging.getLogger("meld")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    yield log_file

    logger.removeHandler(handler)
    handler.close()


# ============================================================================
# Cleanup Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def cleanup_meld_dirs(tmp_path: Path):
    """Ensure meld directories are cleaned up after tests."""
    yield
    # Cleanup happens automatically with tmp_path


# ============================================================================
# Test Configuration
# ============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow tests")
    config.addinivalue_line("markers", "benchmark: Performance benchmarks")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Add markers based on test location."""
    for item in items:
        # Add markers based on test file path
        if "/unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
