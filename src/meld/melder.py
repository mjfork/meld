"""Melder component for plan generation and synthesis."""

import json
import re
from dataclasses import dataclass

from meld.data_models import AdvisorResult, ConvergenceAssessment, ConvergenceStatus
from meld.prompts import INITIAL_PLAN_PROMPT, SYNTHESIS_PROMPT
from meld.providers import ClaudeAdapter


@dataclass
class MelderResult:
    """Result from melder operation."""

    plan: str
    convergence: ConvergenceAssessment | None = None
    decision_log: str = ""
    raw_output: str = ""


class Melder:
    """The Melder component that generates and synthesizes plans."""

    def __init__(self, timeout: int = 600) -> None:
        """Initialize the Melder."""
        self._adapter = ClaudeAdapter(timeout=timeout)

    async def generate_initial_plan(
        self,
        task: str,
        prd_context: str | None = None,
    ) -> MelderResult:
        """Generate the initial plan from a task description."""
        prompt = INITIAL_PLAN_PROMPT.format(
            task=task,
            prd_context=prd_context or "No additional context provided.",
        )

        result = await self._adapter.invoke(prompt)

        if not result.success:
            raise RuntimeError(f"Melder failed: {result.error}")

        plan = self._extract_plan(result.feedback)
        return MelderResult(plan=plan, raw_output=result.feedback)

    async def synthesize_feedback(
        self,
        current_plan: str,
        advisor_results: list[AdvisorResult],
        round_number: int,
    ) -> MelderResult:
        """Synthesize advisor feedback into an updated plan."""
        feedback_text = self._format_advisor_feedback(advisor_results)

        prompt = SYNTHESIS_PROMPT.format(
            current_plan=current_plan,
            advisor_feedback=feedback_text,
            round_number=round_number,
        )

        result = await self._adapter.invoke(prompt)

        if not result.success:
            raise RuntimeError(f"Melder synthesis failed: {result.error}")

        plan = self._extract_plan(result.feedback)
        convergence = self._extract_convergence(result.feedback)
        decision_log = self._extract_decision_log(result.feedback)

        return MelderResult(
            plan=plan,
            convergence=convergence,
            decision_log=decision_log,
            raw_output=result.feedback,
        )

    def _format_advisor_feedback(self, results: list[AdvisorResult]) -> str:
        """Format advisor results into a prompt section."""
        sections = []
        for result in results:
            if result.success:
                sections.append(f"## {result.provider.upper()} Feedback\n{result.feedback}")
            else:
                sections.append(f"## {result.provider.upper()} (Failed)\nNo feedback available.")
        return "\n\n".join(sections)

    def _extract_plan(self, output: str) -> str:
        """Extract the plan content from melder output."""
        # Look for plan section markers
        plan_match = re.search(
            r"(?:## Plan|# Plan|## Updated Plan|# Updated Plan)\s*\n(.*?)(?=\n## |\n# |\Z)",
            output,
            re.DOTALL | re.IGNORECASE,
        )
        if plan_match:
            return plan_match.group(1).strip()

        # If no markers, return the whole output as the plan
        return output.strip()

    def _extract_convergence(self, output: str) -> ConvergenceAssessment | None:
        """Extract convergence assessment from melder output."""
        # Look for JSON convergence block
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", output, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                status_str = data.get("STATUS", "CONTINUING").upper()
                status = (
                    ConvergenceStatus.CONVERGED
                    if status_str == "CONVERGED"
                    else ConvergenceStatus.CONTINUING
                )
                return ConvergenceAssessment(
                    status=status,
                    changes_made=data.get("CHANGES_MADE", 0),
                    open_items=data.get("OPEN_ITEMS", 0),
                    rationale=data.get("RATIONALE", ""),
                )
            except json.JSONDecodeError:
                pass

        # Look for inline markers
        if "STATUS: CONVERGED" in output.upper():
            return ConvergenceAssessment(
                status=ConvergenceStatus.CONVERGED,
                changes_made=0,
                open_items=0,
            )

        return None

    def _extract_decision_log(self, output: str) -> str:
        """Extract decision log from melder output."""
        log_match = re.search(
            r"(?:## Decision Log|# Decision Log)\s*\n(.*?)(?=\n## |\n# |\Z)",
            output,
            re.DOTALL | re.IGNORECASE,
        )
        if log_match:
            return log_match.group(1).strip()
        return ""
