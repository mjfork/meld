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

    def test_resume_restores_current_round(self, temp_run_dir: Path) -> None:
        """Current round is restored when resuming."""
        original = SessionManager(task="Test task", run_dir=str(temp_run_dir))
        original.write_plan("Plan 1", round_number=1)
        original.write_plan("Plan 2", round_number=2)
        original.update_metadata(rounds_completed=2)
        original.mark_interrupted()
        session_id = original.session_id

        resumed = SessionManager(
            task="Ignored",
            run_dir=str(temp_run_dir),
            resume_id=session_id,
        )

        assert resumed.current_round == 2


class TestEventsJsonl:
    """Tests for events.jsonl functionality."""

    def test_append_event(self, temp_run_dir: Path) -> None:
        """Events are appended to events.jsonl."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        manager.append_event("test_event", data="value1")
        manager.append_event("test_event", data="value2")

        events_path = manager.session_path / "events.jsonl"
        assert events_path.exists()

        lines = events_path.read_text().strip().split("\n")
        assert len(lines) == 2

        event1 = json.loads(lines[0])
        assert event1["type"] == "test_event"
        assert event1["data"] == "value1"
        assert "timestamp" in event1

        event2 = json.loads(lines[1])
        assert event2["data"] == "value2"

    def test_append_event_no_save_mode(self, temp_run_dir: Path) -> None:
        """No events written in no-save mode."""
        manager = SessionManager(
            task="Test task",
            run_dir=str(temp_run_dir),
            no_save=True,
        )

        manager.append_event("test_event", data="value")

        events_path = manager.session_path / "events.jsonl"
        assert not events_path.exists()

    def test_write_plan_logs_event(self, temp_run_dir: Path) -> None:
        """Writing a plan creates an event."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        manager.write_plan("Test plan", round_number=1)

        events_path = manager.session_path / "events.jsonl"
        lines = events_path.read_text().strip().split("\n")

        plan_events = [json.loads(line) for line in lines if json.loads(line)["type"] == "plan_written"]
        assert len(plan_events) >= 1
        assert plan_events[-1]["round"] == 1

    def test_write_advisor_feedback_logs_event(self, temp_run_dir: Path) -> None:
        """Writing advisor feedback creates an event."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        manager.write_advisor_feedback("claude", "Feedback", round_number=1)

        events_path = manager.session_path / "events.jsonl"
        lines = events_path.read_text().strip().split("\n")

        feedback_events = [
            json.loads(line)
            for line in lines
            if json.loads(line)["type"] == "advisor_feedback"
        ]
        assert len(feedback_events) >= 1
        assert feedback_events[-1]["provider"] == "claude"


class TestAtomicWrites:
    """Tests for atomic write functionality."""

    def test_write_artifact_is_atomic(self, temp_run_dir: Path) -> None:
        """Write artifact uses atomic write pattern."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        # Write multiple times - if not atomic, could see partial content
        for i in range(10):
            manager.write_artifact("test.txt", f"Content {i}")

        # Final content should be complete
        path = manager.session_path / "test.txt"
        assert path.read_text() == "Content 9"

    def test_no_temp_files_left_behind(self, temp_run_dir: Path) -> None:
        """No temporary files left after writes."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        manager.write_artifact("test.txt", "Content")

        # Check no temp files remain
        temp_files = list(manager.session_path.glob(".*test.txt*"))
        assert len(temp_files) == 0


class TestDirectoryPermissions:
    """Tests for directory permissions."""

    def test_session_directory_permissions(self, temp_run_dir: Path) -> None:
        """Session directory has correct permissions."""
        import os
        import stat

        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))

        permissions = stat.S_IMODE(os.stat(manager.session_path).st_mode)
        assert permissions == 0o755


class TestSessionJsonSchema:
    """Tests for enhanced session.json schema."""

    def test_session_json_has_current_round(self, temp_run_dir: Path) -> None:
        """session.json contains current_round."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))
        manager.write_plan("Plan", round_number=3)

        session_file = manager.session_path / "session.json"
        data = json.loads(session_file.read_text())

        assert data["current_round"] == 3

    def test_session_json_has_advisors_status(self, temp_run_dir: Path) -> None:
        """session.json contains advisor statuses."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))
        manager.write_advisor_feedback("claude", "Feedback", round_number=1)
        manager.write_advisor_feedback("gemini", "More feedback", round_number=1)

        session_file = manager.session_path / "session.json"
        data = json.loads(session_file.read_text())

        assert "advisors" in data
        assert data["advisors"]["claude"] == "completed"
        assert data["advisors"]["gemini"] == "completed"

    def test_session_json_has_convergence_info(self, temp_run_dir: Path) -> None:
        """session.json contains convergence information."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))
        manager.update_convergence("continuing", open_items=3, diff_ratio=0.15)

        session_file = manager.session_path / "session.json"
        data = json.loads(session_file.read_text())

        assert "convergence" in data
        assert data["convergence"]["status"] == "continuing"
        assert data["convergence"]["open_items"] == 3
        assert data["convergence"]["diff_ratio"] == 0.15

    def test_session_json_has_interrupted_at(self, temp_run_dir: Path) -> None:
        """session.json contains interrupted_at when interrupted."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))
        manager.mark_interrupted()

        session_file = manager.session_path / "session.json"
        data = json.loads(session_file.read_text())

        assert data["interrupted_at"] is not None
        assert data["status"] == "interrupted"


class TestGetLastCheckpoint:
    """Tests for get_last_checkpoint functionality."""

    def test_get_last_checkpoint_basic(self, temp_run_dir: Path) -> None:
        """get_last_checkpoint returns basic info."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))
        manager.write_plan("Plan 1", round_number=1)
        manager.write_plan("Plan 2", round_number=2)
        manager.mark_interrupted()

        checkpoint = manager.get_last_checkpoint()

        assert checkpoint["session_id"] == manager.session_id
        assert checkpoint["current_round"] == 2
        assert checkpoint["status"] == "interrupted"

    def test_get_last_checkpoint_finds_plan_files(self, temp_run_dir: Path) -> None:
        """get_last_checkpoint finds latest plan file."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))
        manager.write_plan("Plan 0", round_number=0)
        manager.write_plan("Plan 1", round_number=1)
        manager.write_plan("Plan 2", round_number=2)

        checkpoint = manager.get_last_checkpoint()

        assert checkpoint["last_plan_round"] == 2
        assert "plan.round2.md" in checkpoint["last_plan_file"]

    def test_get_last_checkpoint_lists_advisors_completed(self, temp_run_dir: Path) -> None:
        """get_last_checkpoint lists completed advisors."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))
        manager.write_advisor_feedback("claude", "Feedback", round_number=1)
        manager.write_advisor_feedback("gemini", "Feedback", round_number=1)

        checkpoint = manager.get_last_checkpoint()

        assert "claude" in checkpoint["advisors_completed"]
        assert "gemini" in checkpoint["advisors_completed"]

    def test_get_last_checkpoint_feedback_received(self, temp_run_dir: Path) -> None:
        """get_last_checkpoint lists feedback received for current round."""
        manager = SessionManager(task="Test task", run_dir=str(temp_run_dir))
        manager.write_plan("Plan", round_number=1)
        manager.write_advisor_feedback("claude", "Feedback", round_number=1)
        manager.write_advisor_feedback("gemini", "Feedback", round_number=1)

        checkpoint = manager.get_last_checkpoint()

        assert "claude" in checkpoint["feedback_received"]
        assert "gemini" in checkpoint["feedback_received"]


class TestListSessions:
    """Tests for list_sessions class method."""

    def test_list_sessions_empty(self, temp_run_dir: Path) -> None:
        """list_sessions returns empty list when no sessions."""
        sessions = SessionManager.list_sessions(str(temp_run_dir))
        assert sessions == []

    def test_list_sessions_finds_all(self, temp_run_dir: Path) -> None:
        """list_sessions finds all sessions."""
        # Create multiple sessions
        s1 = SessionManager(task="Task 1", run_dir=str(temp_run_dir))
        s2 = SessionManager(task="Task 2", run_dir=str(temp_run_dir))
        s3 = SessionManager(task="Task 3", run_dir=str(temp_run_dir))

        sessions = SessionManager.list_sessions(str(temp_run_dir))

        assert len(sessions) == 3
        tasks = [s["task"] for s in sessions]
        assert "Task 1" in tasks
        assert "Task 2" in tasks
        assert "Task 3" in tasks

    def test_list_sessions_sorted_by_started(self, temp_run_dir: Path) -> None:
        """list_sessions returns sessions sorted by started time."""
        import time

        s1 = SessionManager(task="Task 1", run_dir=str(temp_run_dir))
        time.sleep(0.1)
        s2 = SessionManager(task="Task 2", run_dir=str(temp_run_dir))
        time.sleep(0.1)
        s3 = SessionManager(task="Task 3", run_dir=str(temp_run_dir))

        sessions = SessionManager.list_sessions(str(temp_run_dir))

        # Most recent first
        assert sessions[0]["task"] == "Task 3"
        assert sessions[1]["task"] == "Task 2"
        assert sessions[2]["task"] == "Task 1"
