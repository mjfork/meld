"""End-to-end happy path tests for meld."""

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meld.data_models import AdvisorResult, ConvergenceAssessment, ConvergenceStatus
from meld.melder import MelderResult
from meld.orchestrator import run_meld

# Configure detailed logging for E2E tests
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("meld.e2e")


class TestHappyPath:
    """End-to-end tests for successful meld workflows."""

    @pytest.fixture
    def mock_full_system(self, temp_run_dir: Path):
        """Mock the complete system for E2E testing."""
        with patch("meld.orchestrator.Melder") as MockMelder, \
             patch("meld.orchestrator.AdvisorPool") as MockPool, \
             patch("meld.orchestrator.run_preflight") as mock_preflight:

            # Configure preflight to pass
            mock_preflight.return_value = [
                MagicMock(cli_found=True, auth_valid=True, provider="claude"),
                MagicMock(cli_found=True, auth_valid=True, provider="gemini"),
                MagicMock(cli_found=True, auth_valid=True, provider="openai"),
            ]

            # Track rounds for convergence simulation
            round_counter = [0]

            # Configure melder
            melder = MockMelder.return_value

            async def generate_plan(task, prd_context=None):
                logger.info(f"E2E: Generating initial plan for task: {task[:50]}...")
                return MelderResult(
                    plan=f"""## Overview
Comprehensive plan for: {task}

## Steps
1. Analyze requirements
2. Design architecture
3. Implement core functionality
4. Add error handling
5. Write tests
6. Document changes

## Considerations
- Performance implications
- Security best practices
- Maintainability

## Risks
- Scope creep
- Integration challenges
""",
                    raw_output="Initial plan generated",
                )

            async def synthesize(current_plan, advisor_results, round_number):
                round_counter[0] = round_number
                logger.info(f"E2E: Synthesizing round {round_number}")
                logger.info(f"E2E: Received {len([r for r in advisor_results if r.success])} feedback items")

                if round_number >= 3:
                    logger.info("E2E: Convergence reached!")
                    return MelderResult(
                        plan=current_plan + "\n\n## Final Refinements\n- All feedback incorporated",
                        convergence=ConvergenceAssessment(
                            status=ConvergenceStatus.CONVERGED,
                            changes_made=0,
                            open_items=0,
                            rationale="All concerns addressed",
                        ),
                        decision_log="ACCEPTED: All improvements\nCONVERGED",
                        raw_output="Final synthesis",
                    )

                return MelderResult(
                    plan=current_plan + f"\n\n## Round {round_number} Updates\n- Applied feedback",
                    convergence=ConvergenceAssessment(
                        status=ConvergenceStatus.CONTINUING,
                        changes_made=3,
                        open_items=2,
                        rationale="Still improving",
                    ),
                    decision_log=f"Round {round_number}: ACCEPTED several items",
                    raw_output=f"Synthesis round {round_number}",
                )

            melder.generate_initial_plan = generate_plan
            melder.synthesize_feedback = synthesize

            # Configure advisor pool
            pool = MockPool.return_value

            async def collect_feedback(plan, task, prd_context=None, round_number=1):
                logger.info(f"E2E: Collecting feedback for round {round_number}")
                return [
                    AdvisorResult(
                        provider="claude",
                        success=True,
                        feedback="## Improvements\n- Add caching layer\n## Concerns\n- Memory usage",
                        duration_seconds=1.5,
                        round_number=round_number,
                    ),
                    AdvisorResult(
                        provider="gemini",
                        success=True,
                        feedback="## Improvements\n- Consider async\n## Additions\n- Add retries",
                        duration_seconds=1.8,
                        round_number=round_number,
                    ),
                    AdvisorResult(
                        provider="openai",
                        success=True,
                        feedback="## Improvements\n- Error handling\n## Rationale\n- Robustness",
                        duration_seconds=2.0,
                        round_number=round_number,
                    ),
                ]

            pool.collect_feedback = collect_feedback
            pool.advisor_names = ["claude", "gemini", "openai"]
            pool.get_participating_advisors = lambda r: [x.provider for x in r if x.success]

            yield {
                "melder": melder,
                "pool": pool,
                "preflight": mock_preflight,
                "run_dir": str(temp_run_dir),
            }

    def test_simple_task_converges(self, mock_full_system) -> None:
        """Test that a simple task completes successfully."""
        logger.info("E2E TEST: Simple task convergence")

        result = run_meld(
            task="Add user authentication to the application",
            run_dir=mock_full_system["run_dir"],
            quiet=True,
            skip_preflight=True,
        )

        logger.info(f"E2E: Completed in {result.rounds_completed} rounds")
        logger.info(f"E2E: Converged: {result.converged}")
        logger.info(f"E2E: Advisors: {result.advisors_participated}")

        assert result.success
        assert result.converged
        assert result.rounds_completed == 3
        assert len(result.advisors_participated) == 3
        assert "authentication" in result.plan.lower() or "Overview" in result.plan

    def test_with_prd_context(self, mock_full_system, tmp_path: Path) -> None:
        """Test that PRD context is included in the process."""
        logger.info("E2E TEST: With PRD context")

        # Create a PRD file
        prd_file = tmp_path / "requirements.md"
        prd_file.write_text("""# Authentication Requirements

## Goals
- Secure user authentication
- Support OAuth2 providers
- Session management

## Non-Goals
- Social login
- Biometric auth
""")

        result = run_meld(
            task="Implement the authentication system",
            prd_path=str(prd_file),
            run_dir=mock_full_system["run_dir"],
            quiet=True,
            skip_preflight=True,
        )

        logger.info(f"E2E: Result with PRD: {result.success}")

        assert result.success
        assert result.converged

    def test_output_to_file(self, mock_full_system, tmp_path: Path) -> None:
        """Test that output is written to file correctly."""
        logger.info("E2E TEST: Output to file")

        output_file = tmp_path / "final-plan.md"

        result = run_meld(
            task="Design a caching system",
            output_path=str(output_file),
            run_dir=mock_full_system["run_dir"],
            quiet=True,
            skip_preflight=True,
        )

        assert result.success
        assert output_file.exists()

        content = output_file.read_text()
        logger.info(f"E2E: Output file size: {len(content)} chars")

        assert "Meld Plan Output" in content
        assert "caching" in content.lower() or "Overview" in content

    def test_json_output(self, mock_full_system, tmp_path: Path) -> None:
        """Test that JSON output is generated correctly."""
        logger.info("E2E TEST: JSON output")

        json_file = tmp_path / "result.json"

        result = run_meld(
            task="Create an API endpoint",
            json_output_path=str(json_file),
            run_dir=mock_full_system["run_dir"],
            quiet=True,
            skip_preflight=True,
        )

        assert result.success
        assert json_file.exists()

        data = json.loads(json_file.read_text())
        logger.info(f"E2E: JSON output: {json.dumps(data, indent=2)}")

        assert "session_id" in data
        assert "converged" in data
        assert data["converged"] is True
        assert "advisors_participated" in data
        assert len(data["advisors_participated"]) == 3

    def test_session_artifacts_created(self, mock_full_system) -> None:
        """Test that all session artifacts are created."""
        logger.info("E2E TEST: Session artifacts")

        result = run_meld(
            task="Build a notification system",
            run_dir=mock_full_system["run_dir"],
            quiet=True,
            skip_preflight=True,
        )

        session_path = Path(mock_full_system["run_dir"]) / result.session_id
        logger.info(f"E2E: Session path: {session_path}")

        assert session_path.exists()

        # Check expected artifacts
        expected_files = [
            "task.md",
            "plan.round0.md",
            "final-plan.md",
            "session.json",
        ]

        for filename in expected_files:
            file_path = session_path / filename
            assert file_path.exists(), f"Missing: {filename}"
            logger.info(f"E2E: Found artifact: {filename} ({file_path.stat().st_size} bytes)")

        # Check session.json content
        with open(session_path / "session.json") as f:
            session_data = json.load(f)

        assert session_data["status"] == "complete"
        assert session_data["converged"] is True

    def test_custom_max_rounds(self, mock_full_system) -> None:
        """Test that custom max rounds is respected."""
        logger.info("E2E TEST: Custom max rounds")

        # With mock that converges at round 3, setting max_rounds=2 should stop early
        with patch.object(
            mock_full_system["melder"],
            "synthesize_feedback",
            new=AsyncMock(return_value=MelderResult(
                plan="Updated plan",
                convergence=ConvergenceAssessment(
                    status=ConvergenceStatus.CONTINUING,
                    changes_made=1,
                    open_items=1,
                ),
                decision_log="",
                raw_output="",
            )),
        ):
            result = run_meld(
                task="Short task",
                max_rounds=2,
                run_dir=mock_full_system["run_dir"],
                quiet=True,
                skip_preflight=True,
            )

            logger.info(f"E2E: Rounds completed: {result.rounds_completed}")

            assert result.rounds_completed == 2
            assert not result.converged
