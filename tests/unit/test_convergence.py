"""Unit tests for convergence detection."""

import pytest

from meld.convergence import ConvergenceDetector
from meld.data_models import ConvergenceAssessment, ConvergenceStatus


class TestConvergenceDetector:
    """Tests for ConvergenceDetector."""

    def test_never_converges_round_one(self) -> None:
        """Never converges on round 1."""
        detector = ConvergenceDetector(min_rounds=1)

        assessment = ConvergenceAssessment(
            status=ConvergenceStatus.CONVERGED,
            changes_made=0,
            open_items=0,
        )

        result = detector.check_convergence(
            melder_assessment=assessment,
            old_plan="Plan A",
            new_plan="Plan A",
            round_number=0,  # Round 0 (before min_rounds=1)
        )

        assert result.status == ConvergenceStatus.CONTINUING

    def test_converges_when_melder_says_converged(self) -> None:
        """Converges when melder assessment is CONVERGED and diff is small."""
        detector = ConvergenceDetector()

        assessment = ConvergenceAssessment(
            status=ConvergenceStatus.CONVERGED,
            changes_made=0,
            open_items=0,
        )

        # Use identical plans so diff is 0 (passes diff validation)
        result = detector.check_convergence(
            melder_assessment=assessment,
            old_plan="Plan A content",
            new_plan="Plan A content",  # Identical
            round_number=2,
        )

        assert result.status == ConvergenceStatus.CONVERGED

    def test_continues_when_open_items_exist(self) -> None:
        """Continues when OPEN_ITEMS > 0 regardless of status."""
        detector = ConvergenceDetector()

        assessment = ConvergenceAssessment(
            status=ConvergenceStatus.CONVERGED,  # Melder claims converged
            changes_made=0,
            open_items=2,  # But there are open items
        )

        result = detector.check_convergence(
            melder_assessment=assessment,
            old_plan="Plan A",
            new_plan="Plan A",
            round_number=2,
        )

        assert result.status == ConvergenceStatus.CONTINUING
        assert "Open items" in result.rationale

    def test_continues_when_diff_is_large(self) -> None:
        """Continues when melder claims converged but diff is large."""
        detector = ConvergenceDetector()

        assessment = ConvergenceAssessment(
            status=ConvergenceStatus.CONVERGED,
            changes_made=0,
            open_items=0,
        )

        old_plan = "Original plan content"
        new_plan = "Completely different plan with many changes and new sections"

        result = detector.check_convergence(
            melder_assessment=assessment,
            old_plan=old_plan,
            new_plan=new_plan,
            round_number=2,
        )

        assert result.status == ConvergenceStatus.CONTINUING
        assert "diff is large" in result.rationale.lower()

    def test_detects_oscillation(self) -> None:
        """Detects oscillating plans (A -> B -> A)."""
        detector = ConvergenceDetector()

        plan_a = "Plan version A with specific content"
        plan_b = "Plan version B with different content"

        # Round 1: A
        detector.check_convergence(
            melder_assessment=None,
            old_plan="",
            new_plan=plan_a,
            round_number=1,
        )

        # Round 2: B
        detector.check_convergence(
            melder_assessment=None,
            old_plan=plan_a,
            new_plan=plan_b,
            round_number=2,
        )

        # Round 3: A again (oscillation!)
        result = detector.check_convergence(
            melder_assessment=None,
            old_plan=plan_b,
            new_plan=plan_a,
            round_number=3,
        )

        assert result.status == ConvergenceStatus.OSCILLATING

    def test_handles_no_melder_assessment(self) -> None:
        """Works without melder assessment using diff only."""
        detector = ConvergenceDetector(diff_threshold=0.05)

        # Identical plans should converge
        result = detector.check_convergence(
            melder_assessment=None,
            old_plan="Plan content here",
            new_plan="Plan content here",  # Identical
            round_number=2,
        )

        assert result.status == ConvergenceStatus.CONVERGED

    def test_continues_without_assessment_when_diff_large(self) -> None:
        """Continues without assessment when diff is large."""
        detector = ConvergenceDetector(diff_threshold=0.05)

        result = detector.check_convergence(
            melder_assessment=None,
            old_plan="Original",
            new_plan="Completely different content",
            round_number=2,
        )

        assert result.status == ConvergenceStatus.CONTINUING


class TestDiffCalculation:
    """Tests for diff ratio calculation."""

    def test_identical_plans_zero_diff(self) -> None:
        """Identical plans have zero diff."""
        detector = ConvergenceDetector()

        ratio = detector.calculate_diff_ratio(
            "Same content",
            "Same content",
        )

        assert ratio == 0.0

    def test_completely_different_plans_high_diff(self) -> None:
        """Completely different plans have high diff."""
        detector = ConvergenceDetector()

        ratio = detector.calculate_diff_ratio(
            "Plan A content",
            "Completely different B",
        )

        assert ratio > 0.5

    def test_minor_changes_low_diff(self) -> None:
        """Minor changes result in low diff ratio."""
        detector = ConvergenceDetector()

        old_plan = """## Overview
This is the plan overview.

## Steps
1. First step
2. Second step
3. Third step
"""
        new_plan = """## Overview
This is the plan overview.

## Steps
1. First step
2. Second step (updated)
3. Third step
"""
        ratio = detector.calculate_diff_ratio(old_plan, new_plan)

        assert ratio < 0.2


class TestPlanHistory:
    """Tests for plan history tracking."""

    def test_adds_plans_to_history(self) -> None:
        """Plans are added to history."""
        detector = ConvergenceDetector()

        detector.add_plan("Plan 1")
        detector.add_plan("Plan 2")
        detector.add_plan("Plan 3")

        assert len(detector._plan_history) == 3

    def test_oscillation_requires_minimum_history(self) -> None:
        """Oscillation detection requires at least 3 plans."""
        detector = ConvergenceDetector()

        detector.add_plan("Plan A")
        detector.add_plan("Plan B")

        assert detector.detect_oscillation() is False

    def test_no_oscillation_with_different_plans(self) -> None:
        """No oscillation when plans are all different."""
        detector = ConvergenceDetector()

        detector.add_plan("Plan A")
        detector.add_plan("Plan B")
        detector.add_plan("Plan C")

        assert detector.detect_oscillation() is False
