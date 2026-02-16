"""Orchestrator for the meld convergence loop."""

import signal
from dataclasses import dataclass
from pathlib import Path

from meld.advisors import AdvisorPool
from meld.convergence import ConvergenceDetector
from meld.data_models import ConvergenceStatus
from meld.melder import Melder
from meld.output import OutputFormatter
from meld.preflight import run_preflight
from meld.session import SessionManager


@dataclass
class MeldResult:
    """Result of a meld run."""

    success: bool
    plan: str
    session_id: str
    rounds_completed: int
    converged: bool
    advisors_participated: list[str]
    output_path: Path | None = None


class Orchestrator:
    """Orchestrates the meld convergence loop."""

    def __init__(
        self,
        task: str,
        prd_path: str | None = None,
        max_rounds: int = 5,
        timeout: int = 600,
        output_path: str | None = None,
        json_output_path: str | None = None,
        run_dir: str = ".meld/runs",
        resume_id: str | None = None,
        quiet: bool = False,
        verbose: bool = False,
        no_save: bool = False,
        skip_preflight: bool = False,
    ) -> None:
        """Initialize the orchestrator."""
        self._task = task
        self._prd_context = self._load_prd(prd_path) if prd_path else None
        self._max_rounds = max_rounds
        self._timeout = timeout
        self._output_path = output_path
        self._json_output_path = json_output_path
        self._quiet = quiet
        self._verbose = verbose
        self._skip_preflight = skip_preflight

        self._session = SessionManager(
            task=task,
            run_dir=run_dir,
            no_save=no_save,
            prd_path=prd_path,
            resume_id=resume_id,
        )

        self._melder = Melder(timeout=timeout)
        self._advisor_pool = AdvisorPool(timeout=timeout)
        self._convergence = ConvergenceDetector()
        self._output = OutputFormatter(verbose=verbose)

        self._interrupted = False
        self._setup_signal_handlers()

    def _load_prd(self, path: str) -> str:
        """Load PRD content from file."""
        return Path(path).read_text()

    def _setup_signal_handlers(self) -> None:
        """Setup handlers for graceful shutdown."""

        def handler(signum: int, frame: object) -> None:
            self._interrupted = True
            self._session.mark_interrupted()

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    async def run(self) -> MeldResult:
        """Run the meld convergence loop."""

        # Preflight checks
        if not self._skip_preflight:
            results = await run_preflight()
            available = [r for r in results if r.cli_found]
            if not available:
                raise RuntimeError("No provider CLIs available. Run 'meld doctor' for help.")

        # Save initial task
        self._session.write_artifact("task.md", self._task)
        if self._prd_context:
            self._session.write_artifact("prd.md", self._prd_context)

        # Generate initial plan
        if not self._quiet:
            print("Generating initial plan...")

        melder_result = await self._melder.generate_initial_plan(
            self._task,
            self._prd_context,
        )
        current_plan = melder_result.plan
        self._session.write_plan(current_plan, 0)

        all_participants: set[str] = set()
        converged = False
        final_round = 0

        # Convergence loop
        for round_num in range(1, self._max_rounds + 1):
            if self._interrupted:
                break

            final_round = round_num
            if not self._quiet:
                print(f"\n--- Round {round_num}/{self._max_rounds} ---")
                print("Collecting advisor feedback...")

            # Collect feedback
            advisor_results = await self._advisor_pool.collect_feedback(
                plan=current_plan,
                task=self._task,
                prd_context=self._prd_context,
                round_number=round_num,
            )

            # Record participating advisors
            participants = self._advisor_pool.get_participating_advisors(advisor_results)
            all_participants.update(participants)

            # Save feedback
            for result in advisor_results:
                if result.success:
                    self._session.write_advisor_feedback(
                        result.provider,
                        result.feedback,
                        round_num,
                    )

            if not self._quiet:
                print(f"Received feedback from: {', '.join(participants)}")
                print("Synthesizing...")

            # Synthesize feedback
            synthesis = await self._melder.synthesize_feedback(
                current_plan,
                advisor_results,
                round_num,
            )

            # Check convergence
            convergence = self._convergence.check_convergence(
                synthesis.convergence,
                current_plan,
                synthesis.plan,
                round_num,
            )

            current_plan = synthesis.plan
            self._session.write_plan(current_plan, round_num)

            if convergence.status == ConvergenceStatus.CONVERGED:
                if not self._quiet:
                    print("✓ Plan converged!")
                converged = True
                break
            elif convergence.status == ConvergenceStatus.OSCILLATING:
                if not self._quiet:
                    print("⚠ Plan oscillating - needs human decision")
                break

            if not self._quiet:
                print(f"Changes: {convergence.changes_made}, Open items: {convergence.open_items}")

        # Finalize
        self._session.write_final_plan(current_plan)
        self._session.update_metadata(
            rounds_completed=final_round,
            max_rounds=self._max_rounds,
        )
        self._session.mark_complete(converged, list(all_participants))

        # Format and output
        final_output = self._output.format_final_plan(
            plan=current_plan,
            session=self._session.metadata,
            verbose_outputs=None if not self._verbose else [],
        )

        output_file = None
        if self._output_path:
            output_file = Path(self._output_path)
            output_file.write_text(final_output)
        else:
            print("\n" + final_output)

        if self._json_output_path:
            json_output = self._output.format_json_summary(self._session.metadata)
            Path(self._json_output_path).write_text(json_output)

        return MeldResult(
            success=True,
            plan=current_plan,
            session_id=self._session.session_id,
            rounds_completed=final_round,
            converged=converged,
            advisors_participated=list(all_participants),
            output_path=output_file,
        )


async def _run_async(orchestrator: Orchestrator) -> MeldResult:
    """Async wrapper for orchestrator run."""
    return await orchestrator.run()


def run_meld(
    task: str,
    prd_path: str | None = None,
    max_rounds: int = 5,
    timeout: int = 600,
    output_path: str | None = None,
    json_output_path: str | None = None,
    run_dir: str = ".meld/runs",
    resume_id: str | None = None,
    quiet: bool = False,
    verbose: bool = False,
    no_save: bool = False,
    skip_preflight: bool = False,
) -> MeldResult:
    """Run meld synchronously."""
    import asyncio

    orchestrator = Orchestrator(
        task=task,
        prd_path=prd_path,
        max_rounds=max_rounds,
        timeout=timeout,
        output_path=output_path,
        json_output_path=json_output_path,
        run_dir=run_dir,
        resume_id=resume_id,
        quiet=quiet,
        verbose=verbose,
        no_save=no_save,
        skip_preflight=skip_preflight,
    )

    return asyncio.run(_run_async(orchestrator))
