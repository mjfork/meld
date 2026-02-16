"""Data models for meld components."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ProviderErrorType(Enum):
    """Categorized error types for provider failures."""

    CLI_NOT_FOUND = "cli_not_found"
    AUTH_FAILED = "auth_failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    PARSE_ERROR = "parse_error"
    UNKNOWN = "unknown"


class AdvisorStatus(Enum):
    """Status of an advisor during execution."""

    WAITING = "waiting"  # Not yet started
    RUNNING = "running"  # Currently executing
    STREAMING = "streaming"  # Receiving output
    COMPLETE = "complete"  # Finished successfully
    FAILED = "failed"  # Failed after retries
    RETRYING = "retrying"  # Retrying after failure


class ConvergenceStatus(Enum):
    """Status of convergence detection."""

    CONVERGED = "converged"
    CONTINUING = "continuing"
    OSCILLATING = "oscillating"
    NEEDS_HUMAN = "needs_human"


@dataclass
class ProviderError:
    """Error from a provider adapter."""

    error_type: ProviderErrorType
    message: str
    provider: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    retryable: bool = False


@dataclass
class AdvisorResult:
    """Result from an advisor invocation."""

    provider: str
    success: bool
    feedback: str = ""
    error: ProviderError | None = None
    duration_seconds: float = 0.0
    round_number: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class StreamEvent:
    """Event from streaming output."""

    provider: str
    content: str
    is_complete: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ConvergenceAssessment:
    """Assessment of plan convergence."""

    status: ConvergenceStatus
    changes_made: int
    open_items: int
    diff_ratio: float = 0.0
    rationale: str = ""


@dataclass
class PlanDelta:
    """Summary of changes between plan versions."""

    added_sections: list[str] = field(default_factory=list)
    removed_sections: list[str] = field(default_factory=list)
    modified_sections: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class SessionMetadata:
    """Metadata for a meld session."""

    session_id: str
    task: str
    prd_path: str | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    rounds_completed: int = 0
    max_rounds: int = 5
    converged: bool = False
    advisors_participated: list[str] = field(default_factory=list)
    status: str = "running"
