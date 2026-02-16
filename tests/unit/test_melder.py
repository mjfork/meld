"""Unit tests for Melder component."""

from unittest.mock import AsyncMock, patch

import pytest

from meld.data_models import AdvisorResult, ConvergenceStatus
from meld.melder import Melder


class TestMelder:
    """Tests for Melder component."""

    @pytest.fixture
    def mock_claude_invoke(self):
        """Mock Claude adapter invoke method."""
        with patch("meld.melder.ClaudeAdapter") as MockClaude:
            instance = MockClaude.return_value
            instance.invoke = AsyncMock()
            yield instance.invoke

    @pytest.mark.asyncio
    async def test_generate_initial_plan(self, mock_claude_invoke) -> None:
        """Generates initial plan from task."""
        mock_claude_invoke.return_value = AdvisorResult(
            provider="claude",
            success=True,
            feedback="""## Plan
This is the generated plan content.

## Steps
1. First step
2. Second step
""",
        )

        melder = Melder()
        result = await melder.generate_initial_plan("Add authentication")

        assert result.plan is not None
        assert "generated plan" in result.plan.lower() or "step" in result.plan.lower()

    @pytest.mark.asyncio
    async def test_generate_initial_plan_with_prd(self, mock_claude_invoke) -> None:
        """Includes PRD context in plan generation."""
        mock_claude_invoke.return_value = AdvisorResult(
            provider="claude",
            success=True,
            feedback="## Plan\nPlan with PRD context.",
        )

        melder = Melder()
        await melder.generate_initial_plan(
            "Add authentication",
            prd_context="OAuth2 requirements",
        )

        # Verify PRD was included in the prompt
        call_args = mock_claude_invoke.call_args[0][0]
        assert "OAuth2" in call_args

    @pytest.mark.asyncio
    async def test_generate_plan_failure(self, mock_claude_invoke) -> None:
        """Raises error when plan generation fails."""
        mock_claude_invoke.return_value = AdvisorResult(
            provider="claude",
            success=False,
        )

        melder = Melder()

        with pytest.raises(RuntimeError, match="Melder failed"):
            await melder.generate_initial_plan("Add authentication")

    @pytest.mark.asyncio
    async def test_synthesize_feedback(self, mock_claude_invoke) -> None:
        """Synthesizes advisor feedback into updated plan."""
        mock_claude_invoke.return_value = AdvisorResult(
            provider="claude",
            success=True,
            feedback="""## Decision Log
- ACCEPTED: Add error handling

## Updated Plan
Updated plan with improvements.

## Convergence Assessment
```json
{
    "STATUS": "CONTINUING",
    "CHANGES_MADE": 2,
    "OPEN_ITEMS": 1,
    "RATIONALE": "Still improving"
}
```
""",
        )

        melder = Melder()
        advisor_results = [
            AdvisorResult(
                provider="claude",
                success=True,
                feedback="Add error handling",
            ),
            AdvisorResult(
                provider="gemini",
                success=True,
                feedback="Consider performance",
            ),
        ]

        result = await melder.synthesize_feedback(
            current_plan="Original plan",
            advisor_results=advisor_results,
            round_number=1,
        )

        assert result.plan is not None
        assert result.convergence is not None
        assert result.convergence.status == ConvergenceStatus.CONTINUING
        assert result.convergence.changes_made == 2

    @pytest.mark.asyncio
    async def test_synthesize_with_converged_status(self, mock_claude_invoke) -> None:
        """Detects converged status from synthesis."""
        mock_claude_invoke.return_value = AdvisorResult(
            provider="claude",
            success=True,
            feedback="""## Updated Plan
Final plan.

## Convergence Assessment
```json
{
    "STATUS": "CONVERGED",
    "CHANGES_MADE": 0,
    "OPEN_ITEMS": 0,
    "RATIONALE": "No more changes needed"
}
```
""",
        )

        melder = Melder()
        result = await melder.synthesize_feedback(
            current_plan="Plan",
            advisor_results=[],
            round_number=5,
        )

        assert result.convergence is not None
        assert result.convergence.status == ConvergenceStatus.CONVERGED

    @pytest.mark.asyncio
    async def test_extracts_decision_log(self, mock_claude_invoke) -> None:
        """Extracts decision log from synthesis output."""
        mock_claude_invoke.return_value = AdvisorResult(
            provider="claude",
            success=True,
            feedback="""## Decision Log
- ACCEPTED: Error handling - improves reliability
- REJECTED: Complex caching - overkill for v1
- DEFERRED: Metrics - nice to have later

## Updated Plan
Plan content.
""",
        )

        melder = Melder()
        result = await melder.synthesize_feedback(
            current_plan="Plan",
            advisor_results=[],
            round_number=1,
        )

        assert "ACCEPTED" in result.decision_log
        assert "REJECTED" in result.decision_log

    @pytest.mark.asyncio
    async def test_handles_failed_advisors(self, mock_claude_invoke) -> None:
        """Handles mix of successful and failed advisor results."""
        mock_claude_invoke.return_value = AdvisorResult(
            provider="claude",
            success=True,
            feedback="## Updated Plan\nPlan updated with available feedback.",
        )

        melder = Melder()
        advisor_results = [
            AdvisorResult(provider="claude", success=True, feedback="Good feedback"),
            AdvisorResult(provider="gemini", success=False, feedback=""),
            AdvisorResult(provider="openai", success=True, feedback="More feedback"),
        ]

        result = await melder.synthesize_feedback(
            current_plan="Plan",
            advisor_results=advisor_results,
            round_number=1,
        )

        # Verify the prompt mentions failed advisor
        call_args = mock_claude_invoke.call_args[0][0]
        assert "Failed" in call_args or "gemini" in call_args.lower()


class TestPlanExtraction:
    """Tests for plan content extraction."""

    def test_extracts_plan_section(self) -> None:
        """Extracts plan from marked section."""
        melder = Melder()

        output = """Some preamble.

## Plan
This is the plan content.
With multiple lines.

## Other Section
Other content.
"""
        plan = melder._extract_plan(output)

        assert "This is the plan content" in plan
        assert "Other content" not in plan

    def test_handles_missing_markers(self) -> None:
        """Returns full output when no plan markers found."""
        melder = Melder()

        output = "Just some content without markers."
        plan = melder._extract_plan(output)

        assert plan == output.strip()


class TestConvergenceExtraction:
    """Tests for convergence assessment extraction."""

    def test_extracts_json_assessment(self) -> None:
        """Extracts convergence from JSON block."""
        melder = Melder()

        output = """
Some content.

```json
{
    "STATUS": "CONVERGED",
    "CHANGES_MADE": 0,
    "OPEN_ITEMS": 0,
    "RATIONALE": "All done"
}
```
"""
        convergence = melder._extract_convergence(output)

        assert convergence is not None
        assert convergence.status == ConvergenceStatus.CONVERGED
        assert convergence.changes_made == 0

    def test_extracts_inline_status(self) -> None:
        """Extracts convergence from inline markers."""
        melder = Melder()

        output = "The plan is complete. STATUS: CONVERGED"
        convergence = melder._extract_convergence(output)

        assert convergence is not None
        assert convergence.status == ConvergenceStatus.CONVERGED

    def test_returns_none_when_no_assessment(self) -> None:
        """Returns None when no assessment found."""
        melder = Melder()

        output = "Just a regular response without convergence info."
        convergence = melder._extract_convergence(output)

        assert convergence is None
