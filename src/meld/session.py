"""Session management and persistence."""

import json
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from meld.data_models import SessionMetadata


class SessionManager:
    """Manages session state and artifact persistence."""

    # Common secret patterns to redact
    SECRET_PATTERNS = [
        (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_API_KEY]"),
        (r"api[_-]?key['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9-_]{20,}", "[REDACTED_API_KEY]"),
        (r"token['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9-_]{20,}", "[REDACTED_TOKEN]"),
        (r"password['\"]?\s*[:=]\s*['\"]?[^\s'\"]{8,}", "[REDACTED_PASSWORD]"),
    ]

    # Directory permissions for session directories
    DIR_PERMISSIONS = 0o755

    def __init__(
        self,
        task: str,
        run_dir: str = ".meld/runs",
        no_save: bool = False,
        prd_path: str | None = None,
        resume_id: str | None = None,
    ) -> None:
        """Initialize session manager."""
        self._no_save = no_save
        self._run_dir = Path(run_dir)
        self._current_round = 0
        self._interrupted_at: datetime | None = None
        self._advisor_statuses: dict[str, str] = {}
        self._convergence_info: dict[str, Any] = {}

        if resume_id:
            self._session_id = resume_id
            self._session_path = self._run_dir / resume_id
            self._metadata = self._load_metadata()
            # Restore additional state from loaded metadata
            self._current_round = self._metadata.rounds_completed
        else:
            self._session_id = self._generate_session_id()
            self._session_path = self._run_dir / self._session_id
            self._metadata = SessionMetadata(
                session_id=self._session_id,
                task=task,
                prd_path=prd_path,
            )

        if not no_save:
            self._create_session_directory()
            self._save_metadata()

    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._session_id

    @property
    def session_path(self) -> Path:
        """Get the session directory path."""
        return self._session_path

    @property
    def metadata(self) -> SessionMetadata:
        """Get session metadata."""
        return self._metadata

    @property
    def current_round(self) -> int:
        """Get current round number."""
        return self._current_round

    def _generate_session_id(self) -> str:
        """Generate a unique session ID.

        Format: YYYYMMDD-HHMMSS-<8char hex>
        Example: 20260116-024717-abc12345
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        return f"{timestamp}-{short_uuid}"

    def _create_session_directory(self) -> None:
        """Create the session directory with proper permissions."""
        self._session_path.mkdir(parents=True, exist_ok=True)
        # Set directory permissions
        os.chmod(self._session_path, self.DIR_PERMISSIONS)

    def _load_metadata(self) -> SessionMetadata:
        """Load metadata from existing session."""
        meta_path = self._session_path / "session.json"
        if meta_path.exists():
            with open(meta_path) as f:
                data = json.load(f)

            # Load additional session state (not part of SessionMetadata)
            self._current_round = data.get("current_round", 0)
            self._advisor_statuses = data.get("advisors", {})
            self._convergence_info = data.get("convergence", {})
            if data.get("interrupted_at"):
                self._interrupted_at = datetime.fromisoformat(data["interrupted_at"])

            # Extract only the fields that SessionMetadata expects
            metadata_fields = {
                "session_id": data.get("session_id"),
                "task": data.get("task"),
                "prd_path": data.get("prd_path"),
                "rounds_completed": data.get("rounds_completed", 0),
                "max_rounds": data.get("max_rounds", 5),
                "converged": data.get("converged", False),
                "advisors_participated": data.get("advisors_participated", []),
                "status": data.get("status", "running"),
            }

            # Convert ISO date strings back to datetime objects
            if data.get("started_at"):
                metadata_fields["started_at"] = datetime.fromisoformat(data["started_at"])
            if data.get("completed_at"):
                metadata_fields["completed_at"] = datetime.fromisoformat(data["completed_at"])

            return SessionMetadata(**metadata_fields)
        raise FileNotFoundError(f"Session not found: {self._session_id}")

    def redact_secrets(self, content: str) -> str:
        """Redact common secret patterns from content."""
        for pattern, replacement in self.SECRET_PATTERNS:
            content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
        return content

    def _atomic_write(self, path: Path, content: str) -> None:
        """Write content to file atomically using temp file + rename."""
        # Create temp file in same directory to ensure same filesystem
        fd, temp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            # Atomic rename
            os.replace(temp_path, path)
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def write_artifact(self, filename: str, content: str, redact: bool = True) -> Path | None:
        """Write an artifact to the session directory atomically."""
        if self._no_save:
            return None

        if redact:
            content = self.redact_secrets(content)

        path = self._session_path / filename
        self._atomic_write(path, content)
        return path

    def write_json(self, filename: str, data: dict[str, Any]) -> Path | None:
        """Write JSON data to the session directory atomically."""
        if self._no_save:
            return None

        content = json.dumps(data, indent=2, default=str)
        path = self._session_path / filename
        self._atomic_write(path, content)
        return path

    def append_event(self, event_type: str, **data: Any) -> None:
        """Append an event to events.jsonl."""
        if self._no_save:
            return

        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": event_type,
            **data,
        }

        events_path = self._session_path / "events.jsonl"
        line = json.dumps(event, default=str) + "\n"

        # Append mode is safe for crash recovery - each line is independent
        with open(events_path, "a") as f:
            f.write(line)

    def update_metadata(self, **kwargs: Any) -> None:
        """Update session metadata."""
        for key, value in kwargs.items():
            if hasattr(self._metadata, key):
                setattr(self._metadata, key, value)
        self._save_metadata()

    def _save_metadata(self) -> None:
        """Save metadata to session.json."""
        if self._no_save:
            return

        data = {
            "id": self._metadata.session_id,
            "session_id": self._metadata.session_id,  # Keep for backwards compatibility
            "status": self._metadata.status,
            "current_round": self._current_round,
            "interrupted_at": (
                self._interrupted_at.isoformat() if self._interrupted_at else None
            ),
            "max_rounds": self._metadata.max_rounds,
            "started": self._metadata.started_at.isoformat(),
            "updated": datetime.utcnow().isoformat(),
            "config": {
                "timeout": 600,  # Default timeout
                "prd_file": self._metadata.prd_path,
            },
            "advisors": self._advisor_statuses,
            "convergence": self._convergence_info,
            # Legacy fields for backwards compatibility
            "task": self._metadata.task,
            "prd_path": self._metadata.prd_path,
            "started_at": self._metadata.started_at.isoformat(),
            "completed_at": (
                self._metadata.completed_at.isoformat() if self._metadata.completed_at else None
            ),
            "rounds_completed": self._metadata.rounds_completed,
            "converged": self._metadata.converged,
            "advisors_participated": self._metadata.advisors_participated,
        }
        self.write_json("session.json", data)

    def write_plan(self, plan: str, round_number: int) -> Path | None:
        """Write a plan snapshot for a specific round."""
        self._current_round = round_number
        self.append_event("plan_written", round=round_number, length=len(plan))
        result = self.write_artifact(f"plan.round{round_number}.md", plan)
        self._save_metadata()  # Update session.json with new current_round
        return result

    def write_advisor_feedback(self, provider: str, feedback: str, round_number: int) -> Path | None:
        """Write advisor feedback for a specific round."""
        self._advisor_statuses[provider] = "completed"
        self.append_event(
            "advisor_feedback",
            provider=provider,
            round=round_number,
            length=len(feedback),
        )
        result = self.write_artifact(f"advisor.{provider}.round{round_number}.md", feedback)
        self._save_metadata()  # Update session.json with advisor status
        return result

    def update_advisor_status(self, provider: str, status: str) -> None:
        """Update the status of an advisor."""
        self._advisor_statuses[provider] = status
        self.append_event("advisor_status_change", provider=provider, status=status)
        self._save_metadata()

    def update_convergence(
        self,
        status: str,
        open_items: int = 0,
        diff_ratio: float = 0.0,
    ) -> None:
        """Update convergence information."""
        self._convergence_info = {
            "status": status,
            "open_items": open_items,
            "diff_ratio": diff_ratio,
        }
        self.append_event(
            "convergence_update",
            status=status,
            open_items=open_items,
            diff_ratio=diff_ratio,
        )
        self._save_metadata()

    def write_final_plan(self, plan: str) -> Path | None:
        """Write the final converged plan."""
        self.append_event("final_plan_written", length=len(plan))
        return self.write_artifact("final-plan.md", plan)

    def mark_complete(self, converged: bool, advisors: list[str]) -> None:
        """Mark the session as complete."""
        self.append_event(
            "session_complete",
            converged=converged,
            advisors=advisors,
            rounds=self._current_round,
        )
        self.update_metadata(
            completed_at=datetime.utcnow(),
            converged=converged,
            advisors_participated=advisors,
            status="complete",
        )

    def mark_interrupted(self) -> None:
        """Mark the session as interrupted."""
        self._interrupted_at = datetime.utcnow()
        self.append_event("session_interrupted", round=self._current_round)
        self.update_metadata(status="interrupted")

    def get_last_checkpoint(self) -> dict[str, Any]:
        """Get the last checkpoint for resume.

        Returns information about where to resume from.
        """
        checkpoint = {
            "session_id": self._session_id,
            "current_round": self._current_round,
            "status": self._metadata.status,
            "advisors_completed": [
                provider
                for provider, status in self._advisor_statuses.items()
                if status == "completed"
            ],
        }

        # Find the latest plan
        plan_files = sorted(
            self._session_path.glob("plan.round*.md"),
            key=lambda p: int(p.stem.split("round")[1]),
            reverse=True,
        )
        if plan_files:
            checkpoint["last_plan_file"] = str(plan_files[0])
            checkpoint["last_plan_round"] = int(plan_files[0].stem.split("round")[1])

        # Find advisor feedback for current round
        advisor_files = list(
            self._session_path.glob(f"advisor.*.round{self._current_round}.md")
        )
        checkpoint["feedback_received"] = [
            f.stem.split(".")[1] for f in advisor_files
        ]

        return checkpoint

    @classmethod
    def list_sessions(cls, run_dir: str = ".meld/runs") -> list[dict[str, Any]]:
        """List all sessions in the run directory."""
        sessions: list[dict[str, Any]] = []
        run_path = Path(run_dir)
        if not run_path.exists():
            return sessions

        for session_dir in run_path.iterdir():
            if not session_dir.is_dir():
                continue
            session_file = session_dir / "session.json"
            if session_file.exists():
                with open(session_file) as f:
                    data = json.load(f)
                sessions.append(data)

        return sorted(sessions, key=lambda s: s.get("started", ""), reverse=True)
