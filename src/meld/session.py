"""Session management and persistence."""

import json
import re
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

        if resume_id:
            self._session_id = resume_id
            self._session_path = self._run_dir / resume_id
            self._metadata = self._load_metadata()
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

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        return f"{timestamp}-{short_uuid}"

    def _create_session_directory(self) -> None:
        """Create the session directory."""
        self._session_path.mkdir(parents=True, exist_ok=True)

    def _load_metadata(self) -> SessionMetadata:
        """Load metadata from existing session."""
        meta_path = self._session_path / "session.json"
        if meta_path.exists():
            with open(meta_path) as f:
                data = json.load(f)

            # Convert ISO date strings back to datetime objects
            if data.get("started_at"):
                data["started_at"] = datetime.fromisoformat(data["started_at"])
            if data.get("completed_at"):
                data["completed_at"] = datetime.fromisoformat(data["completed_at"])

            return SessionMetadata(**data)
        raise FileNotFoundError(f"Session not found: {self._session_id}")

    def redact_secrets(self, content: str) -> str:
        """Redact common secret patterns from content."""
        for pattern, replacement in self.SECRET_PATTERNS:
            content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
        return content

    def write_artifact(self, filename: str, content: str, redact: bool = True) -> Path | None:
        """Write an artifact to the session directory."""
        if self._no_save:
            return None

        if redact:
            content = self.redact_secrets(content)

        path = self._session_path / filename
        path.write_text(content)
        return path

    def write_json(self, filename: str, data: dict[str, Any]) -> Path | None:
        """Write JSON data to the session directory."""
        if self._no_save:
            return None

        content = json.dumps(data, indent=2, default=str)
        path = self._session_path / filename
        path.write_text(content)
        return path

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
            "session_id": self._metadata.session_id,
            "task": self._metadata.task,
            "prd_path": self._metadata.prd_path,
            "started_at": self._metadata.started_at.isoformat(),
            "completed_at": (
                self._metadata.completed_at.isoformat() if self._metadata.completed_at else None
            ),
            "rounds_completed": self._metadata.rounds_completed,
            "max_rounds": self._metadata.max_rounds,
            "converged": self._metadata.converged,
            "advisors_participated": self._metadata.advisors_participated,
            "status": self._metadata.status,
        }
        self.write_json("session.json", data)

    def write_plan(self, plan: str, round_number: int) -> Path | None:
        """Write a plan snapshot for a specific round."""
        return self.write_artifact(f"plan.round{round_number}.md", plan)

    def write_advisor_feedback(self, provider: str, feedback: str, round_number: int) -> Path | None:
        """Write advisor feedback for a specific round."""
        return self.write_artifact(f"advisor.{provider}.round{round_number}.md", feedback)

    def write_final_plan(self, plan: str) -> Path | None:
        """Write the final converged plan."""
        return self.write_artifact("final-plan.md", plan)

    def mark_complete(self, converged: bool, advisors: list[str]) -> None:
        """Mark the session as complete."""
        self.update_metadata(
            completed_at=datetime.utcnow(),
            converged=converged,
            advisors_participated=advisors,
            status="complete",
        )

    def mark_interrupted(self) -> None:
        """Mark the session as interrupted."""
        self.update_metadata(status="interrupted")
