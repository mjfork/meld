"""Integration tests for full meld loop with mock components."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meld.advisors import AdvisorPool
from meld.convergence import ConvergenceDetector
from meld.data_models import AdvisorResult, ConvergenceAssessment, ConvergenceStatus
from meld.melder import Melder, MelderResult
from meld.session import SessionManager
from tests.mocks.mock_adapter import MockAdapter


class TestFullLoopIntegration:
    """Integration tests for the full meld convergence loop."""

    @pytest.fixture
    def mock_melder(self):
        """Create a mock melder that returns predictable results."""
        with patch.object(Melder, "__init__", lambda self, **kwargs: None):
            melder = Melder.__new__(Melder)

            call_count = [0]
            last_plan = [None]  # Track last plan for identical return on convergence

            async def generate_plan(task, prd_context=None):
                return MelderResult(
                    plan="## Overview\nInitial plan for: " + task,
                    raw_output="Raw initial plan",
                )

            async def synthesize(current_plan, advisor_results, round_number):
                call_count[0] += 1
                if call_count[0] >= 3:
                    # Return identical plan when converging (so diff is 0)
                    return MelderResult(
                        plan=current_plan,  # No changes - identical to input
                        convergence=ConvergenceAssessment(
                            status=ConvergenceStatus.CONVERGED,
                            changes_made=0,
                            open_items=0,
                        ),
                        decision_log="All feedback incorporated",
                        raw_output="Raw synthesis",
                    )
                new_plan = current_plan + f"\n## Round {round_number} updates"
                last_plan[0] = new_plan
                return MelderResult(
                    plan=new_plan,
                    convergence=ConvergenceAssessment(
                        status=ConvergenceStatus.CONTINUING,
                        changes_made=2,
                        open_items=1,
                    ),
                    decision_log=f"Round {round_number} decisions",
                    raw_output="Raw synthesis",
                )

            melder.generate_initial_plan = generate_plan
            melder.synthesize_feedback = synthesize

            yield melder

    @pytest.fixture
    def mock_advisor_pool(self):
        """Create a mock advisor pool with mock adapters."""
        adapters = [
            MockAdapter(name="claude", delay=0.01),
            MockAdapter(name="gemini", delay=0.01),
            MockAdapter(name="openai", delay=0.01),
        ]

        async def collect_feedback(plan, task, prd_context=None, round_number=1):
            import asyncio
            results = await asyncio.gather(*[
                adapter.invoke(f"Review plan for round {round_number}")
                for adapter in adapters
            ])
            for r in results:
                r.round_number = round_number
            return results

        pool = MagicMock(spec=AdvisorPool)
        pool.collect_feedback = collect_feedback
        pool.advisor_names = ["claude", "gemini", "openai"]
        pool.get_participating_advisors = lambda results: [
            r.provider for r in results if r.success
        ]

        return pool

    @pytest.mark.asyncio
    async def test_full_loop_converges(
        self,
        mock_melder,
        mock_advisor_pool,
        temp_run_dir: Path,
    ) -> None:
        """Tests that full loop converges after expected rounds."""
        session = SessionManager(
            task="Test task for integration",
            run_dir=str(temp_run_dir),
        )
        convergence = ConvergenceDetector(min_rounds=1)

        # Generate initial plan
        initial = await mock_melder.generate_initial_plan("Test task")
        current_plan = initial.plan
        session.write_plan(current_plan, 0)

        converged = False
        rounds_completed = 0

        for round_num in range(1, 6):
            # Collect feedback
            results = await mock_advisor_pool.collect_feedback(
                plan=current_plan,
                task="Test task",
                round_number=round_num,
            )

            # Save feedback
            for result in results:
                if result.success:
                    session.write_advisor_feedback(
                        result.provider,
                        result.feedback,
                        round_num,
                    )

            # Synthesize
            synthesis = await mock_melder.synthesize_feedback(
                current_plan,
                results,
                round_num,
            )

            # Check convergence
            assessment = convergence.check_convergence(
                synthesis.convergence,
                current_plan,
                synthesis.plan,
                round_num,
            )

            current_plan = synthesis.plan
            session.write_plan(current_plan, round_num)
            rounds_completed = round_num

            if assessment.status == ConvergenceStatus.CONVERGED:
                converged = True
                break

        # Should converge after 3 rounds (based on mock_melder setup)
        assert converged
        assert rounds_completed == 3

        # Verify artifacts
        session.mark_complete(converged=True, advisors=["claude", "gemini", "openai"])
        assert (session.session_path / "plan.round0.md").exists()
        assert (session.session_path / "plan.round3.md").exists()

    @pytest.mark.asyncio
    async def test_loop_handles_advisor_failures(
        self,
        mock_melder,
        temp_run_dir: Path,
    ) -> None:
        """Tests that loop continues with partial advisor success."""
        from meld.data_models import ProviderError, ProviderErrorType

        session = SessionManager(
            task="Test task",
            run_dir=str(temp_run_dir),
        )

        # Create pool with one failing adapter
        adapters = [
            MockAdapter(name="claude", delay=0.01),
            MockAdapter(name="gemini", delay=0.01),
            MockAdapter(name="openai", delay=0.01),
        ]
        adapters[1].set_error(ProviderErrorType.AUTH_FAILED)

        async def collect_feedback_with_failure(**kwargs):
            import asyncio
            results = await asyncio.gather(*[
                adapter.invoke("Test") for adapter in adapters
            ])
            return results

        # Run one round
        results = await collect_feedback_with_failure()

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        assert len(successful) == 2
        assert len(failed) == 1

        # Synthesis should still work with partial feedback
        synthesis = await mock_melder.synthesize_feedback(
            "Current plan",
            results,
            round_number=1,
        )

        assert synthesis.plan is not None

    @pytest.mark.asyncio
    async def test_loop_respects_max_rounds(
        self,
        mock_advisor_pool,
        temp_run_dir: Path,
    ) -> None:
        """Tests that loop stops at max rounds even without convergence."""
        # Create melder that never converges
        with patch.object(Melder, "__init__", lambda self, **kwargs: None):
            melder = Melder.__new__(Melder)

            async def never_converge(current_plan, advisor_results, round_number):
                return MelderResult(
                    plan=current_plan + f"\n## Round {round_number}",
                    convergence=ConvergenceAssessment(
                        status=ConvergenceStatus.CONTINUING,
                        changes_made=1,
                        open_items=1,
                    ),
                    decision_log="Still working",
                    raw_output="Raw",
                )

            melder.generate_initial_plan = AsyncMock(
                return_value=MelderResult(plan="Initial", raw_output="")
            )
            melder.synthesize_feedback = never_converge

            convergence = ConvergenceDetector()
            max_rounds = 3
            rounds_completed = 0

            current_plan = "Initial plan"
            for round_num in range(1, max_rounds + 1):
                results = await mock_advisor_pool.collect_feedback(
                    plan=current_plan,
                    task="Task",
                    round_number=round_num,
                )

                synthesis = await melder.synthesize_feedback(
                    current_plan,
                    results,
                    round_num,
                )

                assessment = convergence.check_convergence(
                    synthesis.convergence,
                    current_plan,
                    synthesis.plan,
                    round_num,
                )

                current_plan = synthesis.plan
                rounds_completed = round_num

                if assessment.status == ConvergenceStatus.CONVERGED:
                    break

            assert rounds_completed == max_rounds

    @pytest.mark.asyncio
    async def test_oscillation_detection_in_loop(self, temp_run_dir: Path) -> None:
        """Tests that oscillation is detected during the loop."""
        convergence = ConvergenceDetector()

        plans = [
            "Plan version A with specific content",
            "Plan version B with different content",
            "Plan version A with specific content",  # Back to A
        ]

        old_plan = ""
        detected_oscillation = False

        for i, new_plan in enumerate(plans):
            assessment = convergence.check_convergence(
                melder_assessment=None,
                old_plan=old_plan,
                new_plan=new_plan,
                round_number=i + 1,
            )

            if assessment.status == ConvergenceStatus.OSCILLATING:
                detected_oscillation = True
                break

            old_plan = new_plan

        assert detected_oscillation
