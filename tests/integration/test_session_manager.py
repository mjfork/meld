"""Integration tests for session manager."""

import json
from pathlib import Path

import pytest

from meld.session import SessionManager


class TestSessionManagerIntegration:
    """Integration tests for SessionManager with file system."""

    def test_full_session_lifecycle(self, temp_run_dir: Path) -> None:
        """Tests complete session from creation to completion."""
        # Create session
        manager = SessionManager(
            task="Integration test task",
            run_dir=str(temp_run_dir),
        )

        # Write various artifacts
        manager.write_artifact("task.md", "Integration test task")
        manager.write_plan("Initial plan content", round_number=0)
        manager.write_advisor_feedback("claude", "Claude feedback", round_number=1)
        manager.write_advisor_feedback("gemini", "Gemini feedback", round_number=1)
        manager.write_plan("Updated plan content", round_number=1)

        # Update metadata
        manager.update_metadata(rounds_completed=1)

        # Mark complete
        manager.mark_complete(converged=True, advisors=["claude", "gemini"])

        # Write final plan
        manager.write_final_plan("Final plan content")

        # Verify all files exist
        session_path = manager.session_path
        assert (session_path / "task.md").exists()
        assert (session_path / "plan.round0.md").exists()
        assert (session_path / "plan.round1.md").exists()
        assert (session_path / "advisor.claude.round1.md").exists()
        assert (session_path / "advisor.gemini.round1.md").exists()
        assert (session_path / "final-plan.md").exists()
        assert (session_path / "session.json").exists()

        # Verify session.json content
        with open(session_path / "session.json") as f:
            data = json.load(f)

        assert data["status"] == "complete"
        assert data["converged"] is True
        assert data["rounds_completed"] == 1
        assert "claude" in data["advisors_participated"]
        assert "gemini" in data["advisors_participated"]

    def test_resume_and_continue(self, temp_run_dir: Path) -> None:
        """Tests resuming a session and continuing work."""
        # Create and partially complete a session
        original = SessionManager(
            task="Original task",
            run_dir=str(temp_run_dir),
        )
        original.write_plan("Plan from round 1", round_number=1)
        original.update_metadata(rounds_completed=1)
        original.mark_interrupted()
        session_id = original.session_id

        # Resume the session
        resumed = SessionManager(
            task="Ignored",
            run_dir=str(temp_run_dir),
            resume_id=session_id,
        )

        assert resumed.metadata.status == "interrupted"
        assert resumed.metadata.rounds_completed == 1

        # Continue work
        resumed.write_plan("Plan from round 2", round_number=2)
        resumed.update_metadata(rounds_completed=2)
        resumed.mark_complete(converged=True, advisors=["claude"])

        # Verify final state
        assert resumed.metadata.status == "complete"
        assert resumed.metadata.rounds_completed == 2
        assert (resumed.session_path / "plan.round2.md").exists()

    def test_secret_redaction_in_artifacts(self, temp_run_dir: Path) -> None:
        """Tests that secrets are redacted from written artifacts."""
        manager = SessionManager(
            task="Test task",
            run_dir=str(temp_run_dir),
        )

        content_with_secrets = """
        The API key is sk-abc123def456ghi789jklmnop.
        And the password="mysupersecretpassword".
        Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
        """

        path = manager.write_artifact("with_secrets.md", content_with_secrets)
        assert path is not None

        written_content = path.read_text()
        assert "sk-abc123def456" not in written_content
        assert "mysupersecret" not in written_content
        assert "[REDACTED" in written_content

    def test_no_save_mode_writes_nothing(self, temp_run_dir: Path) -> None:
        """Tests that no-save mode doesn't write any files."""
        manager = SessionManager(
            task="Test task",
            run_dir=str(temp_run_dir),
            no_save=True,
        )

        # Try to write various artifacts
        manager.write_artifact("task.md", "Task content")
        manager.write_plan("Plan content", round_number=0)
        manager.write_advisor_feedback("claude", "Feedback", round_number=1)
        manager.write_final_plan("Final plan")
        manager.update_metadata(rounds_completed=1)

        # Verify nothing was written
        assert not manager.session_path.exists()

    def test_multiple_concurrent_sessions(self, temp_run_dir: Path) -> None:
        """Tests that multiple sessions can coexist."""
        sessions = []
        for i in range(3):
            session = SessionManager(
                task=f"Task {i}",
                run_dir=str(temp_run_dir),
            )
            session.write_plan(f"Plan for task {i}", round_number=0)
            sessions.append(session)

        # All sessions should have unique IDs and paths
        ids = [s.session_id for s in sessions]
        paths = [s.session_path for s in sessions]

        assert len(set(ids)) == 3
        assert len(set(paths)) == 3

        # All session directories should exist
        for session in sessions:
            assert session.session_path.exists()
            assert (session.session_path / "plan.round0.md").exists()
