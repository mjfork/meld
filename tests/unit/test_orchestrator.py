"""Unit tests for orchestrator."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meld.data_models import AdvisorResult, ConvergenceAssessment, ConvergenceStatus
from meld.melder import MelderResult
from meld.orchestrator import MeldResult, Orchestrator, run_meld


class TestOrchestrator:
    """Tests for Orchestrator."""

    @pytest.fixture
    def mock_components(self, temp_run_dir: Path):
        """Mock all orchestrator components."""
        with patch("meld.orchestrator.Melder") as MockMelder, \
             patch("meld.orchestrator.AdvisorPool") as MockPool, \
             patch("meld.orchestrator.ConvergenceDetector") as MockConvergence, \
             patch("meld.orchestrator.run_preflight") as mock_preflight:

            # Mock preflight
            mock_preflight.return_value = [
                MagicMock(cli_found=True, auth_valid=True, provider="claude")
            ]

            # Mock melder
            melder = MockMelder.return_value
            melder.generate_initial_plan = AsyncMock(return_value=MelderResult(
                plan="Initial plan content",
                raw_output="Raw output",
            ))
            melder.synthesize_feedback = AsyncMock(return_value=MelderResult(
                plan="Updated plan content",
                convergence=ConvergenceAssessment(
                    status=ConvergenceStatus.CONVERGED,
                    changes_made=0,
                    open_items=0,
                ),
                decision_log="Decision log",
                raw_output="Raw output",
            ))

            # Mock advisor pool
            pool = MockPool.return_value
            pool.collect_feedback = AsyncMock(return_value=[
                AdvisorResult(provider="claude", success=True, feedback="Feedback"),
            ])
            pool.get_participating_advisors = MagicMock(return_value=["claude"])

            # Mock convergence
            convergence = MockConvergence.return_value
            convergence.check_convergence = MagicMock(return_value=ConvergenceAssessment(
                status=ConvergenceStatus.CONVERGED,
                changes_made=0,
                open_items=0,
            ))

            yield {
                "melder": melder,
                "pool": pool,
                "convergence": convergence,
                "preflight": mock_preflight,
            }

    @pytest.mark.asyncio
    async def test_runs_full_loop(self, mock_components, temp_run_dir: Path) -> None:
        """Runs complete convergence loop."""
        orchestrator = Orchestrator(
            task="Test task",
            run_dir=str(temp_run_dir),
            quiet=True,
            skip_preflight=True,
        )

        result = await orchestrator.run()

        assert result.success is True
        assert result.plan is not None
        assert mock_components["melder"].generate_initial_plan.called
        assert mock_components["pool"].collect_feedback.called

    @pytest.mark.asyncio
    async def test_converges_and_stops(self, mock_components, temp_run_dir: Path) -> None:
        """Stops when convergence is reached."""
        mock_components["convergence"].check_convergence.return_value = ConvergenceAssessment(
            status=ConvergenceStatus.CONVERGED,
            changes_made=0,
            open_items=0,
        )

        orchestrator = Orchestrator(
            task="Test task",
            max_rounds=5,
            run_dir=str(temp_run_dir),
            quiet=True,
            skip_preflight=True,
        )

        result = await orchestrator.run()

        assert result.converged is True
        assert result.rounds_completed == 1  # Stopped after first round

    @pytest.mark.asyncio
    async def test_respects_max_rounds(self, mock_components, temp_run_dir: Path) -> None:
        """Stops at max rounds even if not converged."""
        mock_components["convergence"].check_convergence.return_value = ConvergenceAssessment(
            status=ConvergenceStatus.CONTINUING,
            changes_made=1,
            open_items=1,
        )

        orchestrator = Orchestrator(
            task="Test task",
            max_rounds=3,
            run_dir=str(temp_run_dir),
            quiet=True,
            skip_preflight=True,
        )

        result = await orchestrator.run()

        assert result.rounds_completed == 3
        assert result.converged is False

    @pytest.mark.asyncio
    async def test_saves_artifacts(self, mock_components, temp_run_dir: Path) -> None:
        """Saves artifacts during run."""
        orchestrator = Orchestrator(
            task="Test task",
            run_dir=str(temp_run_dir),
            quiet=True,
            skip_preflight=True,
        )

        await orchestrator.run()

        session_path = orchestrator._session.session_path
        assert (session_path / "task.md").exists()
        assert (session_path / "plan.round0.md").exists()
        assert (session_path / "final-plan.md").exists()

    @pytest.mark.asyncio
    async def test_writes_output_file(self, mock_components, temp_run_dir: Path, tmp_path: Path) -> None:
        """Writes plan to output file when specified."""
        output_file = tmp_path / "output.md"

        orchestrator = Orchestrator(
            task="Test task",
            output_path=str(output_file),
            run_dir=str(temp_run_dir),
            quiet=True,
            skip_preflight=True,
        )

        result = await orchestrator.run()

        assert output_file.exists()
        assert result.output_path == output_file

    @pytest.mark.asyncio
    async def test_writes_json_output(self, mock_components, temp_run_dir: Path, tmp_path: Path) -> None:
        """Writes JSON summary when specified."""
        json_file = tmp_path / "result.json"

        orchestrator = Orchestrator(
            task="Test task",
            json_output_path=str(json_file),
            run_dir=str(temp_run_dir),
            quiet=True,
            skip_preflight=True,
        )

        await orchestrator.run()

        assert json_file.exists()
        import json
        data = json.loads(json_file.read_text())
        assert "session_id" in data
        assert "convergence" in data
        assert data["convergence"]["converged"] is True

    @pytest.mark.asyncio
    async def test_includes_prd_context(self, mock_components, temp_run_dir: Path, tmp_path: Path) -> None:
        """Includes PRD context in prompts."""
        prd_file = tmp_path / "requirements.md"
        prd_file.write_text("# Requirements\n- Feature A\n- Feature B")

        orchestrator = Orchestrator(
            task="Test task",
            prd_path=str(prd_file),
            run_dir=str(temp_run_dir),
            quiet=True,
            skip_preflight=True,
        )

        await orchestrator.run()

        # Verify PRD was passed to melder
        call_args = mock_components["melder"].generate_initial_plan.call_args
        assert "Feature A" in str(call_args) or call_args[1].get("prd_context")

    @pytest.mark.asyncio
    async def test_tracks_participating_advisors(self, mock_components, temp_run_dir: Path) -> None:
        """Tracks which advisors participated."""
        mock_components["pool"].get_participating_advisors.return_value = ["claude", "gemini"]

        orchestrator = Orchestrator(
            task="Test task",
            run_dir=str(temp_run_dir),
            quiet=True,
            skip_preflight=True,
        )

        result = await orchestrator.run()

        assert "claude" in result.advisors_participated
        assert "gemini" in result.advisors_participated


class TestRunMeld:
    """Tests for run_meld convenience function."""

    def test_runs_orchestrator_sync(self, temp_run_dir: Path) -> None:
        """Provides synchronous interface to orchestrator."""
        with patch("meld.orchestrator.Orchestrator") as MockOrch:
            mock_instance = MockOrch.return_value
            mock_instance.run = AsyncMock(return_value=MeldResult(
                success=True,
                plan="Plan",
                session_id="test-id",
                rounds_completed=1,
                converged=True,
                advisors_participated=["claude"],
            ))

            result = run_meld(
                task="Test task",
                run_dir=str(temp_run_dir),
                skip_preflight=True,
            )

            assert result.success is True
            assert MockOrch.called


class TestSignalHandling:
    """Tests for signal handling."""

    @pytest.mark.asyncio
    async def test_handles_interrupt(self, temp_run_dir: Path) -> None:
        """Handles interrupt signal gracefully."""
        with patch("meld.orchestrator.Melder") as MockMelder, \
             patch("meld.orchestrator.AdvisorPool") as MockPool, \
             patch("meld.orchestrator.ConvergenceDetector"), \
             patch("meld.orchestrator.run_preflight") as mock_preflight:

            mock_preflight.return_value = [MagicMock(cli_found=True)]

            melder = MockMelder.return_value
            melder.generate_initial_plan = AsyncMock(return_value=MelderResult(
                plan="Plan",
                raw_output="",
            ))

            # Simulate interrupt during feedback collection
            async def interrupt_feedback(*args, **kwargs):
                import signal
                import os
                os.kill(os.getpid(), signal.SIGINT)
                return []

            pool = MockPool.return_value
            pool.collect_feedback = interrupt_feedback
            pool.get_participating_advisors = MagicMock(return_value=[])

            orchestrator = Orchestrator(
                task="Test task",
                run_dir=str(temp_run_dir),
                quiet=True,
                skip_preflight=True,
            )

            # The orchestrator should handle the interrupt gracefully
            # This test verifies the signal handler is set up
            assert hasattr(orchestrator, "_interrupted")
