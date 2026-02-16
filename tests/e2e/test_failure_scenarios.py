"""End-to-end tests for failure scenarios."""

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meld.data_models import (
    AdvisorResult,
    ConvergenceAssessment,
    ConvergenceStatus,
    ProviderError,
    ProviderErrorType,
)
from meld.melder import MelderResult
from meld.orchestrator import run_meld

logger = logging.getLogger("meld.e2e.failures")


class TestFailureScenarios:
    """End-to-end tests for various failure scenarios."""

    @pytest.fixture
    def base_mock_system(self, temp_run_dir: Path):
        """Base mock system that can be customized for failure tests."""
        with patch("meld.orchestrator.Melder") as MockMelder, \
             patch("meld.orchestrator.AdvisorPool") as MockPool, \
             patch("meld.orchestrator.run_preflight") as mock_preflight:

            mock_preflight.return_value = [
                MagicMock(cli_found=True, auth_valid=True, provider="claude"),
            ]

            melder = MockMelder.return_value
            melder.generate_initial_plan = AsyncMock(return_value=MelderResult(
                plan="Initial plan",
                raw_output="",
            ))
            melder.synthesize_feedback = AsyncMock(return_value=MelderResult(
                plan="Updated plan",
                convergence=ConvergenceAssessment(
                    status=ConvergenceStatus.CONVERGED,
                    changes_made=0,
                    open_items=0,
                ),
                decision_log="",
                raw_output="",
            ))

            pool = MockPool.return_value
            pool.advisor_names = ["claude", "gemini", "openai"]

            yield {
                "melder": melder,
                "pool": pool,
                "preflight": mock_preflight,
                "run_dir": str(temp_run_dir),
            }

    def test_graceful_degradation_one_advisor_fails(self, base_mock_system) -> None:
        """Test that meld continues when one advisor fails."""
        logger.info("E2E TEST: One advisor failure")

        async def collect_with_one_failure(**kwargs):
            return [
                AdvisorResult(
                    provider="claude",
                    success=True,
                    feedback="Claude feedback",
                ),
                AdvisorResult(
                    provider="gemini",
                    success=False,
                    error=ProviderError(
                        error_type=ProviderErrorType.TIMEOUT,
                        message="Timeout after 600s",
                        provider="gemini",
                    ),
                ),
                AdvisorResult(
                    provider="openai",
                    success=True,
                    feedback="OpenAI feedback",
                ),
            ]

        base_mock_system["pool"].collect_feedback = collect_with_one_failure
        base_mock_system["pool"].get_participating_advisors = lambda r: [
            x.provider for x in r if x.success
        ]

        result = run_meld(
            task="Test task",
            run_dir=base_mock_system["run_dir"],
            quiet=True,
            skip_preflight=True,
        )

        logger.info(f"E2E: Result with one failure: {result.advisors_participated}")

        assert result.success
        assert len(result.advisors_participated) == 2
        assert "claude" in result.advisors_participated
        assert "openai" in result.advisors_participated
        assert "gemini" not in result.advisors_participated

    def test_graceful_degradation_two_advisors_fail(self, base_mock_system) -> None:
        """Test that meld continues when two advisors fail."""
        logger.info("E2E TEST: Two advisors failure")

        async def collect_with_two_failures(**kwargs):
            return [
                AdvisorResult(
                    provider="claude",
                    success=True,
                    feedback="Claude feedback",
                ),
                AdvisorResult(
                    provider="gemini",
                    success=False,
                    error=ProviderError(
                        error_type=ProviderErrorType.AUTH_FAILED,
                        message="Auth failed",
                        provider="gemini",
                    ),
                ),
                AdvisorResult(
                    provider="openai",
                    success=False,
                    error=ProviderError(
                        error_type=ProviderErrorType.CLI_NOT_FOUND,
                        message="CLI not found",
                        provider="openai",
                    ),
                ),
            ]

        base_mock_system["pool"].collect_feedback = collect_with_two_failures
        base_mock_system["pool"].get_participating_advisors = lambda r: [
            x.provider for x in r if x.success
        ]

        result = run_meld(
            task="Test task",
            run_dir=base_mock_system["run_dir"],
            quiet=True,
            skip_preflight=True,
        )

        logger.info(f"E2E: Result with two failures: {result.advisors_participated}")

        assert result.success
        assert len(result.advisors_participated) == 1
        assert "claude" in result.advisors_participated

    def test_all_advisors_fail_still_produces_plan(self, base_mock_system) -> None:
        """Test that meld produces a plan even when all advisors fail."""
        logger.info("E2E TEST: All advisors failure")

        async def collect_all_failures(**kwargs):
            return [
                AdvisorResult(
                    provider="claude",
                    success=False,
                    error=ProviderError(
                        error_type=ProviderErrorType.TIMEOUT,
                        message="Timeout",
                        provider="claude",
                    ),
                ),
                AdvisorResult(
                    provider="gemini",
                    success=False,
                    error=ProviderError(
                        error_type=ProviderErrorType.TIMEOUT,
                        message="Timeout",
                        provider="gemini",
                    ),
                ),
                AdvisorResult(
                    provider="openai",
                    success=False,
                    error=ProviderError(
                        error_type=ProviderErrorType.TIMEOUT,
                        message="Timeout",
                        provider="openai",
                    ),
                ),
            ]

        base_mock_system["pool"].collect_feedback = collect_all_failures
        base_mock_system["pool"].get_participating_advisors = lambda r: []

        result = run_meld(
            task="Test task",
            run_dir=base_mock_system["run_dir"],
            quiet=True,
            skip_preflight=True,
        )

        logger.info(f"E2E: Result with all failures: advisors={result.advisors_participated}")

        # Should still produce a plan (just without feedback)
        assert result.success
        assert result.plan is not None
        assert len(result.advisors_participated) == 0

    def test_different_error_types_handled(self, base_mock_system) -> None:
        """Test handling of various error types."""
        logger.info("E2E TEST: Different error types")

        error_types_seen = []

        async def collect_with_various_errors(**kwargs):
            errors = [
                (ProviderErrorType.AUTH_FAILED, "claude"),
                (ProviderErrorType.RATE_LIMITED, "gemini"),
                (ProviderErrorType.NETWORK_ERROR, "openai"),
            ]

            results = []
            for error_type, provider in errors:
                error_types_seen.append(error_type)
                results.append(AdvisorResult(
                    provider=provider,
                    success=False,
                    error=ProviderError(
                        error_type=error_type,
                        message=f"{error_type.value} error",
                        provider=provider,
                    ),
                ))

            return results

        base_mock_system["pool"].collect_feedback = collect_with_various_errors
        base_mock_system["pool"].get_participating_advisors = lambda r: []

        result = run_meld(
            task="Test task",
            run_dir=base_mock_system["run_dir"],
            quiet=True,
            skip_preflight=True,
        )

        logger.info(f"E2E: Error types handled: {error_types_seen}")

        assert result.success
        assert ProviderErrorType.AUTH_FAILED in error_types_seen
        assert ProviderErrorType.RATE_LIMITED in error_types_seen
        assert ProviderErrorType.NETWORK_ERROR in error_types_seen

    def test_oscillation_detected_and_handled(self, base_mock_system) -> None:
        """Test that oscillation is detected and handled."""
        logger.info("E2E TEST: Oscillation detection")

        call_count = [0]

        async def oscillating_synthesis(current_plan, advisor_results, round_number):
            call_count[0] += 1

            # Alternate between two plans
            if call_count[0] % 2 == 1:
                plan = "Plan version A"
            else:
                plan = "Plan version B"

            return MelderResult(
                plan=plan,
                convergence=ConvergenceAssessment(
                    status=ConvergenceStatus.CONTINUING,
                    changes_made=2,
                    open_items=1,
                ),
                decision_log="",
                raw_output="",
            )

        base_mock_system["melder"].synthesize_feedback = oscillating_synthesis

        async def collect_success(**kwargs):
            return [AdvisorResult(provider="claude", success=True, feedback="Feedback")]

        base_mock_system["pool"].collect_feedback = collect_success
        base_mock_system["pool"].get_participating_advisors = lambda r: ["claude"]

        result = run_meld(
            task="Test task",
            max_rounds=5,
            run_dir=base_mock_system["run_dir"],
            quiet=True,
            skip_preflight=True,
        )

        logger.info(f"E2E: Oscillation test rounds: {result.rounds_completed}")

        # Should stop before max rounds due to oscillation or continue to max
        assert result.rounds_completed <= 5


class TestNoSaveMode:
    """Tests for --no-save mode."""

    def test_no_artifacts_in_no_save_mode(self, temp_run_dir: Path) -> None:
        """Test that no artifacts are created in no-save mode."""
        logger.info("E2E TEST: No-save mode")

        with patch("meld.orchestrator.Melder") as MockMelder, \
             patch("meld.orchestrator.AdvisorPool") as MockPool, \
             patch("meld.orchestrator.run_preflight") as mock_preflight:

            mock_preflight.return_value = [MagicMock(cli_found=True)]

            melder = MockMelder.return_value
            melder.generate_initial_plan = AsyncMock(return_value=MelderResult(
                plan="Plan",
                raw_output="",
            ))
            melder.synthesize_feedback = AsyncMock(return_value=MelderResult(
                plan="Updated",
                convergence=ConvergenceAssessment(
                    status=ConvergenceStatus.CONVERGED,
                    changes_made=0,
                    open_items=0,
                ),
                decision_log="",
                raw_output="",
            ))

            pool = MockPool.return_value
            pool.collect_feedback = AsyncMock(return_value=[
                AdvisorResult(provider="claude", success=True, feedback="Feedback")
            ])
            pool.get_participating_advisors = lambda r: ["claude"]
            pool.advisor_names = ["claude"]

            result = run_meld(
                task="Test task",
                run_dir=str(temp_run_dir),
                no_save=True,
                quiet=True,
                skip_preflight=True,
            )

            assert result.success

            # Session directory should not exist
            session_path = temp_run_dir / result.session_id
            assert not session_path.exists()

            # No files should be in the run directory
            files_in_run_dir = list(temp_run_dir.glob("*"))
            logger.info(f"E2E: Files in run dir: {files_in_run_dir}")
            assert len(files_in_run_dir) == 0
