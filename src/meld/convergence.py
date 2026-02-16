"""Convergence detection logic."""

import difflib

from meld.data_models import ConvergenceAssessment, ConvergenceStatus


class ConvergenceDetector:
    """Detects when plan has converged using hybrid approach."""

    def __init__(
        self,
        diff_threshold: float = 0.05,
        min_rounds: int = 1,
    ) -> None:
        """Initialize detector.

        Args:
            diff_threshold: Maximum diff ratio to consider converged (0.05 = 5%)
            min_rounds: Minimum rounds before allowing convergence
        """
        self._diff_threshold = diff_threshold
        self._min_rounds = min_rounds
        self._plan_history: list[str] = []

    def add_plan(self, plan: str) -> None:
        """Add a plan to history for oscillation detection."""
        self._plan_history.append(plan)

    def calculate_diff_ratio(self, old_plan: str, new_plan: str) -> float:
        """Calculate the ratio of changes between two plans."""
        old_lines = old_plan.splitlines()
        new_lines = new_plan.splitlines()

        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        return 1.0 - matcher.ratio()

    def detect_oscillation(self) -> bool:
        """Detect if plan is oscillating (A -> B -> A pattern)."""
        if len(self._plan_history) < 3:
            return False

        # Check if current plan is similar to one from 2 rounds ago
        current = self._plan_history[-1]
        two_ago = self._plan_history[-3]

        diff = self.calculate_diff_ratio(current, two_ago)
        return diff < 0.02  # Less than 2% difference = essentially same

    def check_convergence(
        self,
        melder_assessment: ConvergenceAssessment | None,
        old_plan: str,
        new_plan: str,
        round_number: int,
    ) -> ConvergenceAssessment:
        """Check if convergence has been reached.

        Uses hybrid approach:
        1. Primary: Melder's assessment
        2. Validation: OPEN_ITEMS > 0 means always continue
        3. Secondary: Diff ratio validation
        4. Oscillation detection
        """
        # Never converge on round 1 (need at least one feedback cycle)
        if round_number < self._min_rounds:
            return ConvergenceAssessment(
                status=ConvergenceStatus.CONTINUING,
                changes_made=1,
                open_items=0,
                rationale="Minimum rounds not reached",
            )

        # Add to history for oscillation detection
        self.add_plan(new_plan)

        # Check for oscillation first
        if self.detect_oscillation():
            return ConvergenceAssessment(
                status=ConvergenceStatus.OSCILLATING,
                changes_made=0,
                open_items=0,
                rationale="Plan is oscillating between versions - needs human decision",
            )

        diff_ratio = self.calculate_diff_ratio(old_plan, new_plan)

        # If no melder assessment, use diff-only approach
        if melder_assessment is None:
            if diff_ratio < self._diff_threshold:
                return ConvergenceAssessment(
                    status=ConvergenceStatus.CONVERGED,
                    changes_made=0,
                    open_items=0,
                    diff_ratio=diff_ratio,
                    rationale="Diff below threshold, no explicit assessment",
                )
            return ConvergenceAssessment(
                status=ConvergenceStatus.CONTINUING,
                changes_made=1,
                open_items=0,
                diff_ratio=diff_ratio,
                rationale="No explicit assessment, changes detected",
            )

        # If OPEN_ITEMS > 0, always continue regardless of status
        if melder_assessment.open_items > 0:
            return ConvergenceAssessment(
                status=ConvergenceStatus.CONTINUING,
                changes_made=melder_assessment.changes_made,
                open_items=melder_assessment.open_items,
                diff_ratio=diff_ratio,
                rationale=f"Open items remain: {melder_assessment.open_items}",
            )

        # If melder says CONVERGED but diff is large, treat as CONTINUING
        if melder_assessment.status == ConvergenceStatus.CONVERGED and diff_ratio > 0.1:
            return ConvergenceAssessment(
                status=ConvergenceStatus.CONTINUING,
                changes_made=melder_assessment.changes_made,
                open_items=melder_assessment.open_items,
                diff_ratio=diff_ratio,
                rationale="Melder claims convergence but diff is large",
            )

        # Trust melder's assessment with diff ratio added
        return ConvergenceAssessment(
            status=melder_assessment.status,
            changes_made=melder_assessment.changes_made,
            open_items=melder_assessment.open_items,
            diff_ratio=diff_ratio,
            rationale=melder_assessment.rationale,
        )
