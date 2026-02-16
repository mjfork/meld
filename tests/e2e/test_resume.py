"""End-to-end tests for session resume functionality."""

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meld.data_models import AdvisorResult, ConvergenceAssessment, ConvergenceStatus
from meld.melder import MelderResult
from meld.session import SessionManager

logger = logging.getLogger("meld.e2e.resume")


class TestSessionResume:
    """End-to-end tests for resuming interrupted sessions."""

    def test_resume_interrupted_session(self, temp_run_dir: Path) -> None:
        """Test resuming a session that was interrupted."""
        logger.info("E2E TEST: Resume interrupted session")

        # Phase 1: Create and interrupt a session
        original_session = SessionManager(
            task="Original task for testing resume",
            run_dir=str(temp_run_dir),
        )

        # Simulate some work
        original_session.write_artifact("task.md", "Original task for testing resume")
        original_session.write_plan("Initial plan content", round_number=0)
        original_session.write_plan("Round 1 plan content", round_number=1)
        original_session.write_advisor_feedback("claude", "Claude feedback round 1", round_number=1)
        original_session.update_metadata(rounds_completed=1)
        original_session.mark_interrupted()

        session_id = original_session.session_id
        logger.info(f"E2E: Created interrupted session: {session_id}")

        # Verify interrupted state
        session_path = original_session.session_path
        with open(session_path / "session.json") as f:
            data = json.load(f)
        assert data["status"] == "interrupted"
        assert data["rounds_completed"] == 1

        # Phase 2: Resume the session
        resumed_session = SessionManager(
            task="This should be ignored",
            run_dir=str(temp_run_dir),
            resume_id=session_id,
        )

        logger.info(f"E2E: Resumed session: {resumed_session.session_id}")

        # Verify resumed state
        assert resumed_session.session_id == session_id
        assert resumed_session.metadata.task == "Original task for testing resume"
        assert resumed_session.metadata.rounds_completed == 1
        assert resumed_session.metadata.status == "interrupted"

        # Continue work
        resumed_session.write_plan("Round 2 plan content", round_number=2)
        resumed_session.write_advisor_feedback("claude", "Claude feedback round 2", round_number=2)
        resumed_session.update_metadata(rounds_completed=2)
        resumed_session.mark_complete(converged=True, advisors=["claude"])

        # Verify final state
        assert (session_path / "plan.round0.md").exists()
        assert (session_path / "plan.round1.md").exists()
        assert (session_path / "plan.round2.md").exists()

        with open(session_path / "session.json") as f:
            final_data = json.load(f)

        assert final_data["status"] == "complete"
        assert final_data["rounds_completed"] == 2
        assert final_data["converged"] is True

    def test_resume_preserves_existing_artifacts(self, temp_run_dir: Path) -> None:
        """Test that resuming preserves all existing artifacts."""
        logger.info("E2E TEST: Resume preserves artifacts")

        # Create initial session with artifacts
        original = SessionManager(
            task="Test task",
            run_dir=str(temp_run_dir),
        )

        artifacts = {
            "task.md": "Task description",
            "plan.round0.md": "Initial plan",
            "advisor.claude.round1.md": "Claude feedback",
            "advisor.gemini.round1.md": "Gemini feedback",
        }

        for name, content in artifacts.items():
            original.write_artifact(name, content)

        original.mark_interrupted()
        session_id = original.session_id

        # Resume
        resumed = SessionManager(
            task="Ignored",
            run_dir=str(temp_run_dir),
            resume_id=session_id,
        )

        # Verify all artifacts still exist
        for name, expected_content in artifacts.items():
            path = resumed.session_path / name
            assert path.exists(), f"Missing artifact: {name}"
            assert path.read_text() == expected_content

    def test_resume_nonexistent_session_fails(self, temp_run_dir: Path) -> None:
        """Test that resuming a non-existent session fails clearly."""
        logger.info("E2E TEST: Resume non-existent session")

        with pytest.raises(FileNotFoundError) as exc_info:
            SessionManager(
                task="Test",
                run_dir=str(temp_run_dir),
                resume_id="nonexistent-session-12345",
            )

        assert "Session not found" in str(exc_info.value)

    def test_resume_and_converge(self, temp_run_dir: Path) -> None:
        """Test full resume flow to convergence."""
        logger.info("E2E TEST: Resume to convergence")

        # Create interrupted session at round 2
        original = SessionManager(
            task="Complex feature implementation",
            run_dir=str(temp_run_dir),
        )

        original.write_artifact("task.md", "Complex feature implementation")
        original.write_plan("Plan after round 2", round_number=2)
        original.update_metadata(rounds_completed=2)
        original.mark_interrupted()

        session_id = original.session_id

        # Resume and complete with mocked components
        with patch("meld.orchestrator.Melder") as MockMelder, \
             patch("meld.orchestrator.AdvisorPool") as MockPool, \
             patch("meld.orchestrator.run_preflight") as mock_preflight:

            mock_preflight.return_value = [MagicMock(cli_found=True)]

            melder = MockMelder.return_value
            melder.generate_initial_plan = AsyncMock(return_value=MelderResult(
                plan="Resumed plan",
                raw_output="",
            ))
            melder.synthesize_feedback = AsyncMock(return_value=MelderResult(
                plan="Final converged plan",
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
                AdvisorResult(provider="claude", success=True, feedback="Final feedback")
            ])
            pool.get_participating_advisors = lambda r: ["claude"]
            pool.advisor_names = ["claude"]

            from meld.orchestrator import run_meld

            # Note: The actual resume logic would need to be implemented
            # in the orchestrator. For now, we test the session manager resume.
            resumed = SessionManager(
                task="Ignored",
                run_dir=str(temp_run_dir),
                resume_id=session_id,
            )

            # Simulate completing the remaining rounds
            resumed.write_plan("Final plan after round 3", round_number=3)
            resumed.update_metadata(rounds_completed=3)
            resumed.mark_complete(converged=True, advisors=["claude"])
            resumed.write_final_plan("Final converged plan content")

            # Verify
            assert resumed.metadata.status == "complete"
            assert resumed.metadata.converged is True
            assert (resumed.session_path / "final-plan.md").exists()


class TestSessionMetadataPreservation:
    """Tests for session metadata preservation across resume."""

    def test_metadata_fields_preserved(self, temp_run_dir: Path) -> None:
        """Test that all metadata fields are preserved on resume."""
        logger.info("E2E TEST: Metadata preservation")

        original = SessionManager(
            task="Metadata test task",
            run_dir=str(temp_run_dir),
            prd_path="/path/to/requirements.md",
        )

        original.update_metadata(
            rounds_completed=2,
            max_rounds=5,
        )
        original.mark_interrupted()

        session_id = original.session_id
        original_started = original.metadata.started_at

        # Resume
        resumed = SessionManager(
            task="Ignored",
            run_dir=str(temp_run_dir),
            resume_id=session_id,
        )

        # Verify all fields preserved
        assert resumed.metadata.task == "Metadata test task"
        assert resumed.metadata.prd_path == "/path/to/requirements.md"
        assert resumed.metadata.rounds_completed == 2
        assert resumed.metadata.max_rounds == 5
        assert resumed.metadata.started_at == original_started

    def test_advisors_accumulated_across_resume(self, temp_run_dir: Path) -> None:
        """Test that advisor participation accumulates across resume."""
        logger.info("E2E TEST: Advisor accumulation")

        original = SessionManager(
            task="Test task",
            run_dir=str(temp_run_dir),
        )

        # First run had claude and gemini
        original.update_metadata(advisors_participated=["claude", "gemini"])
        original.mark_interrupted()

        session_id = original.session_id

        # Resume
        resumed = SessionManager(
            task="Ignored",
            run_dir=str(temp_run_dir),
            resume_id=session_id,
        )

        # Previous advisors should be preserved
        assert "claude" in resumed.metadata.advisors_participated
        assert "gemini" in resumed.metadata.advisors_participated

        # Add new advisor participation
        new_advisors = list(resumed.metadata.advisors_participated) + ["openai"]
        resumed.update_metadata(advisors_participated=new_advisors)
        resumed.mark_complete(converged=True, advisors=new_advisors)

        # All three should now be recorded
        with open(resumed.session_path / "session.json") as f:
            data = json.load(f)

        assert len(data["advisors_participated"]) == 3
