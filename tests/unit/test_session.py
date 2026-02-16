"""Unit tests for session manager."""

import json
from pathlib import Path

import pytest

from meld.session import SessionManager


class TestSessionManager:
    """Tests for SessionManager."""

    def test_creates_session_directory(self, temp_run_dir: Path) -> None:
        """Session directory is created on initialization."""
        manager = SessionManager(
            task="Test task",
            run_dir=str(temp_run_dir),
        )

        assert manager.session_path.exists()
        assert manager.session_path.parent == temp_run_dir

    def test_generates_unique_session_id(self, temp_run_dir: Path) -> None:
        """Each session gets a unique ID."""
        manager1 = SessionManager(task="Task 1", run_dir=str(temp_run_dir))
        manager2 = SessionManager(task="Task 2", run_dir=str(temp_run_dir))

        assert manager1.session_id != manager2.session_id

    def test_session_id_format(self, temp_run_dir: Path) -> None:
        """Session ID follows expected format."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        # Format: YYYYMMDD-HHMMSS-<8char hex>
        parts = manager.session_id.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 8  # Date
        assert len(parts[1]) == 6  # Time
        assert len(parts[2]) == 8  # UUID fragment

    def test_no_save_mode_skips_directory(self, temp_run_dir: Path) -> None:
        """No directory created in no-save mode."""
        manager = SessionManager(
            task="Test task",
            run_dir=str(temp_run_dir),
            no_save=True,
        )

        assert not manager.session_path.exists()

    def test_writes_artifact(self, temp_run_dir: Path) -> None:
        """Artifacts are written to session directory."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        path = manager.write_artifact("test.md", "Test content")

        assert path is not None
        assert path.exists()
        assert path.read_text() == "Test content"

    def test_write_artifact_returns_none_in_no_save_mode(self, temp_run_dir: Path) -> None:
        """No artifacts written in no-save mode."""
        manager = SessionManager(
            task="Test task",
            run_dir=str(temp_run_dir),
            no_save=True,
        )

        path = manager.write_artifact("test.md", "Test content")

        assert path is None

    def test_writes_json(self, temp_run_dir: Path) -> None:
        """JSON data is written correctly."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        data = {"key": "value", "number": 42}
        path = manager.write_json("data.json", data)

        assert path is not None
        assert path.exists()

        loaded = json.loads(path.read_text())
        assert loaded == data

    def test_redacts_secrets(self, temp_run_dir: Path) -> None:
        """Secret patterns are redacted from content."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        content = "API key: sk-abc123def456ghi789jkl012"
        redacted = manager.redact_secrets(content)

        assert "sk-abc123" not in redacted
        assert "[REDACTED_API_KEY]" in redacted

    def test_redacts_multiple_secret_patterns(self, temp_run_dir: Path) -> None:
        """Multiple secret patterns are redacted."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        content = """
        api_key = "sk-secretkeyvalue12345678"
        token: "abcdefghijklmnopqrstuvwxyz1234"
        password="mysupersecretpassword123"
        """
        redacted = manager.redact_secrets(content)

        assert "sk-secretkey" not in redacted
        assert "mysupersecret" not in redacted

    def test_write_plan(self, temp_run_dir: Path) -> None:
        """Plan snapshots are written with correct naming."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        path = manager.write_plan("Plan content", round_number=1)

        assert path is not None
        assert path.name == "plan.round1.md"
        assert path.read_text() == "Plan content"

    def test_write_advisor_feedback(self, temp_run_dir: Path) -> None:
        """Advisor feedback is written with correct naming."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        path = manager.write_advisor_feedback("claude", "Feedback content", round_number=2)

        assert path is not None
        assert path.name == "advisor.claude.round2.md"
        assert path.read_text() == "Feedback content"

    def test_write_final_plan(self, temp_run_dir: Path) -> None:
        """Final plan is written correctly."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        path = manager.write_final_plan("Final plan content")

        assert path is not None
        assert path.name == "final-plan.md"
        assert path.read_text() == "Final plan content"

    def test_update_metadata(self, temp_run_dir: Path) -> None:
        """Metadata can be updated."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        manager.update_metadata(rounds_completed=3, converged=True)

        assert manager.metadata.rounds_completed == 3
        assert manager.metadata.converged is True

    def test_mark_complete(self, temp_run_dir: Path) -> None:
        """Session can be marked complete."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        manager.mark_complete(converged=True, advisors=["claude", "gemini"])

        assert manager.metadata.status == "complete"
        assert manager.metadata.converged is True
        assert manager.metadata.advisors_participated == ["claude", "gemini"]
        assert manager.metadata.completed_at is not None

    def test_mark_interrupted(self, temp_run_dir: Path) -> None:
        """Session can be marked interrupted."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        manager.mark_interrupted()

        assert manager.metadata.status == "interrupted"

    def test_saves_session_json(self, temp_run_dir: Path) -> None:
        """Session metadata is saved to session.json."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))
        manager.mark_complete(converged=True, advisors=["claude"])

        session_file = manager.session_path / "session.json"
        assert session_file.exists()

        data = json.loads(session_file.read_text())
        assert data["status"] == "complete"
        assert data["converged"] is True


class TestSessionResume:
    """Tests for session resume functionality."""

    def test_resumes_existing_session(self, temp_run_dir: Path) -> None:
        """Can resume an existing session."""
        # Create original session
        original = SessionManager(task="Original task", run_dir=str(temp_run_dir))
        original.write_plan("Original plan", round_number=1)
        original.update_metadata(rounds_completed=1)
        session_id = original.session_id

        # Resume the session
        resumed = SessionManager(
            task="Ignored",  # Task comes from existing session
            run_dir=str(temp_run_dir),
            resume_id=session_id,
        )

        assert resumed.session_id == session_id
        assert resumed.metadata.task == "Original task"
        assert resumed.metadata.rounds_completed == 1

    def test_resume_nonexistent_session_fails(self, temp_run_dir: Path) -> None:
        """Resuming non-existent session raises error."""
        with pytest.raises(FileNotFoundError):
            SessionManager(
                task="Task",
                run_dir=str(temp_run_dir),
                resume_id="nonexistent-session",
            )
