"""Unit tests for the output formatting module."""

import json
from datetime import datetime, timedelta

import pytest

from meld.data_models import SessionMetadata
from meld.output import OutputFormatter


class TestOutputFormatter:
    """Tests for OutputFormatter."""

    @pytest.fixture
    def basic_session(self) -> SessionMetadata:
        """Create a basic session for testing."""
        now = datetime.utcnow()
        return SessionMetadata(
            session_id="20260116-143045-abc12345",
            task="Build a user authentication system with OAuth2 support",
            started_at=now - timedelta(minutes=5),
            completed_at=now,
            rounds_completed=3,
            max_rounds=5,
            converged=True,
            advisors_participated=["claude", "gemini"],
            status="complete",
        )

    @pytest.fixture
    def non_converged_session(self) -> SessionMetadata:
        """Create a non-converged session for testing."""
        now = datetime.utcnow()
        return SessionMetadata(
            session_id="20260116-143045-def67890",
            task="Design a complex distributed system",
            started_at=now - timedelta(minutes=10),
            completed_at=now,
            rounds_completed=5,
            max_rounds=5,
            converged=False,
            advisors_participated=["claude"],
            status="complete",
        )


class TestFormatFinalPlan:
    """Tests for format_final_plan method."""

    def test_basic_plan_formatting(self, basic_session: SessionMetadata) -> None:
        """Test that basic plan is formatted correctly."""
        formatter = OutputFormatter()
        plan = "## Step 1\nDo something\n\n## Step 2\nDo something else"

        result = formatter.format_final_plan(plan, basic_session)

        assert "# Implementation Plan" in result
        assert plan in result
        assert "## Run Report" in result
        assert basic_session.session_id in result
        assert "Claude ✓" in result
        assert "Gemini ✓" in result
        assert "Openai ✗" in result

    def test_converged_status_text(self, basic_session: SessionMetadata) -> None:
        """Test that converged sessions show correct status."""
        formatter = OutputFormatter()
        result = formatter.format_final_plan("test plan", basic_session)

        assert "Converged after 3 rounds" in result

    def test_non_converged_status_text(self, non_converged_session: SessionMetadata) -> None:
        """Test that non-converged sessions show max rounds status."""
        formatter = OutputFormatter()
        result = formatter.format_final_plan("test plan", non_converged_session)

        assert "Max rounds reached (5/5)" in result

    def test_includes_decision_log(self, basic_session: SessionMetadata) -> None:
        """Test that decision log is included when provided."""
        formatter = OutputFormatter()
        decision_log = "- ACCEPTED: Add OAuth2 flow\n- REJECTED: Skip tests"

        result = formatter.format_final_plan(
            "test plan",
            basic_session,
            decision_log=decision_log,
        )

        assert "### Decision Log" in result
        assert decision_log in result

    def test_includes_round_summaries(self, basic_session: SessionMetadata) -> None:
        """Test that round summaries are included when provided."""
        formatter = OutputFormatter()
        round_summaries = [
            {"round": 1, "changes": 5, "updates": "Added auth flow"},
            {"round": 2, "changes": 2, "updates": "Refined error handling"},
            {"round": 3, "changes": 0, "updates": "No changes"},
        ]

        result = formatter.format_final_plan(
            "test plan",
            basic_session,
            round_summaries=round_summaries,
        )

        assert "### Round Summary" in result
        assert "| Round | Changes | Key Updates |" in result
        assert "| 1 | 5 | Added auth flow |" in result
        assert "| 2 | 2 | Refined error handling |" in result
        assert "| 3 | 0 | No changes |" in result

    def test_verbose_mode_includes_advisor_outputs(self, basic_session: SessionMetadata) -> None:
        """Test that verbose mode includes raw advisor outputs."""
        formatter = OutputFormatter(verbose=True)
        verbose_outputs = [
            "## Claude Output\nSome feedback here",
            "## Gemini Output\nMore feedback here",
        ]

        result = formatter.format_final_plan(
            "test plan",
            basic_session,
            verbose_outputs=verbose_outputs,
        )

        assert "## Raw Advisor Outputs" in result
        assert "## Claude Output" in result
        assert "## Gemini Output" in result

    def test_non_verbose_excludes_advisor_outputs(self, basic_session: SessionMetadata) -> None:
        """Test that non-verbose mode excludes advisor outputs."""
        formatter = OutputFormatter(verbose=False)
        verbose_outputs = ["## Claude Output\nSome feedback here"]

        result = formatter.format_final_plan(
            "test plan",
            basic_session,
            verbose_outputs=verbose_outputs,
        )

        assert "## Raw Advisor Outputs" not in result

    def test_includes_version_footer(self, basic_session: SessionMetadata) -> None:
        """Test that version is included in footer."""
        formatter = OutputFormatter()
        result = formatter.format_final_plan("test plan", basic_session)

        assert "Generated by Meld v" in result


class TestFormatRunReport:
    """Tests for format_run_report method."""

    def test_basic_report_formatting(self, basic_session: SessionMetadata) -> None:
        """Test that basic run report is formatted correctly."""
        formatter = OutputFormatter()
        result = formatter.format_run_report(basic_session)

        assert "# Meld Run Report" in result
        assert basic_session.session_id in result
        assert "Converged after 3 rounds" in result

    def test_includes_timing_info(self, basic_session: SessionMetadata) -> None:
        """Test that timing info is included."""
        formatter = OutputFormatter()
        result = formatter.format_run_report(basic_session)

        assert "**Started:**" in result
        assert "**Completed:**" in result
        assert "**Duration:**" in result

    def test_includes_round_summary_table(self, basic_session: SessionMetadata) -> None:
        """Test that round summary table is present."""
        formatter = OutputFormatter()
        result = formatter.format_run_report(basic_session)

        assert "## Round Summary" in result
        assert "| Round | Changes | Key Updates |" in result

    def test_default_round_entries(self, basic_session: SessionMetadata) -> None:
        """Test that default entries are created for each round."""
        formatter = OutputFormatter()
        result = formatter.format_run_report(basic_session)

        # Should have entries for rounds 1, 2, 3
        assert "| 1 | - | - |" in result
        assert "| 2 | - | - |" in result
        assert "| 3 | - | - |" in result

    def test_custom_round_summaries(self, basic_session: SessionMetadata) -> None:
        """Test that custom round summaries are used."""
        formatter = OutputFormatter()
        round_summaries = [
            {"round": 1, "changes": 8, "updates": "Initial structure"},
        ]

        result = formatter.format_run_report(
            basic_session,
            round_summaries=round_summaries,
        )

        assert "| 1 | 8 | Initial structure |" in result

    def test_includes_decision_log(self, basic_session: SessionMetadata) -> None:
        """Test that decision log is included in run report."""
        formatter = OutputFormatter()
        decision_log = "- ACCEPTED: Use JWT tokens"

        result = formatter.format_run_report(
            basic_session,
            decision_log=decision_log,
        )

        assert "## Decision Log" in result
        assert decision_log in result

    def test_shows_advisor_errors(self, basic_session: SessionMetadata) -> None:
        """Test that advisor errors are reflected in status."""
        formatter = OutputFormatter()
        advisor_errors = {"openai": "CLI not found"}

        result = formatter.format_run_report(
            basic_session,
            advisor_errors=advisor_errors,
        )

        assert "Openai ✗" in result


class TestFormatJsonSummary:
    """Tests for format_json_summary method."""

    def test_valid_json_output(self, basic_session: SessionMetadata) -> None:
        """Test that output is valid JSON."""
        formatter = OutputFormatter()
        result = formatter.format_json_summary(basic_session)

        # Should not raise
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_includes_version(self, basic_session: SessionMetadata) -> None:
        """Test that version is included."""
        formatter = OutputFormatter()
        result = formatter.format_json_summary(basic_session)
        data = json.loads(result)

        assert "version" in data
        assert data["version"] == "0.1.0"

    def test_includes_session_id(self, basic_session: SessionMetadata) -> None:
        """Test that session ID is included."""
        formatter = OutputFormatter()
        result = formatter.format_json_summary(basic_session)
        data = json.loads(result)

        assert data["session_id"] == basic_session.session_id

    def test_includes_status(self, basic_session: SessionMetadata) -> None:
        """Test that status is correct for converged session."""
        formatter = OutputFormatter()
        result = formatter.format_json_summary(basic_session)
        data = json.loads(result)

        assert data["status"] == "converged"

    def test_non_converged_status(self, non_converged_session: SessionMetadata) -> None:
        """Test that status is correct for non-converged session."""
        formatter = OutputFormatter()
        result = formatter.format_json_summary(non_converged_session)
        data = json.loads(result)

        assert data["status"] == "complete"  # Uses session status
        assert data["convergence"]["converged"] is False

    def test_includes_rounds_info(self, basic_session: SessionMetadata) -> None:
        """Test that rounds info is included."""
        formatter = OutputFormatter()
        result = formatter.format_json_summary(basic_session)
        data = json.loads(result)

        assert data["rounds_completed"] == 3
        assert data["max_rounds"] == 5

    def test_includes_duration(self, basic_session: SessionMetadata) -> None:
        """Test that duration is calculated."""
        formatter = OutputFormatter()
        result = formatter.format_json_summary(basic_session)
        data = json.loads(result)

        assert "duration_seconds" in data
        assert data["duration_seconds"] is not None
        assert data["duration_seconds"] > 0

    def test_includes_advisors_object(self, basic_session: SessionMetadata) -> None:
        """Test that advisors object is present."""
        formatter = OutputFormatter()
        result = formatter.format_json_summary(basic_session)
        data = json.loads(result)

        assert "advisors" in data
        assert "claude" in data["advisors"]
        assert data["advisors"]["claude"]["participated"] is True

    def test_includes_convergence_object(self, basic_session: SessionMetadata) -> None:
        """Test that convergence object is present."""
        formatter = OutputFormatter()
        result = formatter.format_json_summary(basic_session)
        data = json.loads(result)

        assert "convergence" in data
        assert data["convergence"]["converged"] is True
        assert "open_items" in data["convergence"]
        assert "final_diff_ratio" in data["convergence"]

    def test_custom_advisor_details(self, basic_session: SessionMetadata) -> None:
        """Test that custom advisor details are used."""
        formatter = OutputFormatter()
        advisor_details = {
            "claude": {"participated": True, "rounds": [1, 2, 3]},
            "gemini": {"participated": True, "rounds": [1, 2, 3]},
            "openai": {"participated": False, "error": "CLI not found"},
        }

        result = formatter.format_json_summary(
            basic_session,
            advisor_details=advisor_details,
        )
        data = json.loads(result)

        assert data["advisors"]["openai"]["participated"] is False
        assert data["advisors"]["openai"]["error"] == "CLI not found"

    def test_custom_convergence_info(self, basic_session: SessionMetadata) -> None:
        """Test that custom convergence info is used."""
        formatter = OutputFormatter()
        convergence_info = {
            "open_items": 0,
            "diff_ratio": 0.02,
        }

        result = formatter.format_json_summary(
            basic_session,
            convergence_info=convergence_info,
        )
        data = json.loads(result)

        assert data["convergence"]["open_items"] == 0
        assert data["convergence"]["final_diff_ratio"] == 0.02

    def test_includes_timestamps(self, basic_session: SessionMetadata) -> None:
        """Test that timestamps are included in ISO format."""
        formatter = OutputFormatter()
        result = formatter.format_json_summary(basic_session)
        data = json.loads(result)

        assert data["started_at"] is not None
        assert data["started_at"].endswith("Z")
        assert data["completed_at"] is not None
        assert data["completed_at"].endswith("Z")


class TestFormatQuietOutput:
    """Tests for format_quiet_output method."""

    def test_returns_plan_only(self, basic_session: SessionMetadata) -> None:
        """Test that quiet mode returns only the plan."""
        formatter = OutputFormatter()
        plan = "This is the plan content."

        result = formatter.format_quiet_output(plan)

        assert result == plan


class TestAdvisorStatusFormatting:
    """Tests for _format_advisor_status helper."""

    def test_all_participated(self) -> None:
        """Test when all advisors participated."""
        formatter = OutputFormatter()
        result = formatter._format_advisor_status(["claude", "gemini", "openai"])

        assert "Claude ✓" in result
        assert "Gemini ✓" in result
        assert "Openai ✓" in result

    def test_partial_participation(self) -> None:
        """Test when only some advisors participated."""
        formatter = OutputFormatter()
        result = formatter._format_advisor_status(["claude"])

        assert "Claude ✓" in result
        assert "Gemini ✗" in result
        assert "Openai ✗" in result

    def test_no_participation(self) -> None:
        """Test when no advisors participated."""
        formatter = OutputFormatter()
        result = formatter._format_advisor_status([])

        assert "Claude ✗" in result
        assert "Gemini ✗" in result
        assert "Openai ✗" in result


# Fixtures available to all test classes
@pytest.fixture
def basic_session() -> SessionMetadata:
    """Create a basic session for testing."""
    now = datetime.utcnow()
    return SessionMetadata(
        session_id="20260116-143045-abc12345",
        task="Build a user authentication system with OAuth2 support",
        started_at=now - timedelta(minutes=5),
        completed_at=now,
        rounds_completed=3,
        max_rounds=5,
        converged=True,
        advisors_participated=["claude", "gemini"],
        status="complete",
    )


@pytest.fixture
def non_converged_session() -> SessionMetadata:
    """Create a non-converged session for testing."""
    now = datetime.utcnow()
    return SessionMetadata(
        session_id="20260116-143045-def67890",
        task="Design a complex distributed system",
        started_at=now - timedelta(minutes=10),
        completed_at=now,
        rounds_completed=5,
        max_rounds=5,
        converged=False,
        advisors_participated=["claude"],
        status="complete",
    )
