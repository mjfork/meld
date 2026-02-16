"""CLI entry point for meld."""

import argparse
import sys
from typing import NoReturn

from meld import __version__


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="meld",
        description="Multi-model planning convergence CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  meld "Add user authentication with OAuth2 support"
  meld --file task.txt --prd requirements.md
  meld --rounds 7 "Design event-driven order processing"
  meld doctor
        """,
    )

    parser.add_argument(
        "--version", "-V", action="version", version=f"%(prog)s {__version__}"
    )

    # Add run arguments
    _add_run_arguments(parser)

    return parser


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    """Add run command arguments to a parser."""
    parser.add_argument("task", nargs="?", help="Task description")
    parser.add_argument("--file", "-f", help="Read task from file")
    parser.add_argument("--prd", help="Include PRD/requirements context")
    parser.add_argument("--rounds", "-r", type=int, default=5, help="Max iteration rounds")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout per advisor (seconds)")
    parser.add_argument("--output", "-o", help="Write plan to file")
    parser.add_argument("--json-output", help="Write JSON summary to file")
    parser.add_argument("--run-dir", default=".meld/runs", help="Run artifacts directory")
    parser.add_argument("--resume", help="Resume interrupted run by ID")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output, no TUI")
    parser.add_argument("--tui", action="store_true", help="Use interactive TUI display")
    parser.add_argument("--verbose", "-v", action="store_true", help="Include raw advisor outputs")
    parser.add_argument("--no-save", action="store_true", help="Don't write artifacts")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip environment checks")


def get_task_input(args: argparse.Namespace) -> str:
    """Get task input from arguments, file, or stdin."""
    if args.task:
        return str(args.task)

    if args.file:
        with open(args.file) as f:
            return f.read().strip()

    if not sys.stdin.isatty():
        return sys.stdin.read().strip()

    raise ValueError("No task provided. Use positional arg, --file, or pipe via stdin.")


def main() -> NoReturn:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Handle doctor command specially
    if args.task == "doctor":
        from meld.preflight import run_doctor

        sys.exit(run_doctor())

    try:
        task = get_task_input(args)
    except ValueError as e:
        parser.error(str(e))

    # Import and run orchestrator
    from meld.orchestrator import run_meld

    result = run_meld(
        task=task,
        prd_path=args.prd,
        max_rounds=args.rounds,
        timeout=args.timeout,
        output_path=args.output,
        json_output_path=args.json_output,
        run_dir=args.run_dir,
        resume_id=args.resume,
        quiet=args.quiet,
        verbose=args.verbose,
        no_save=args.no_save,
        skip_preflight=args.skip_preflight,
        use_tui=args.tui,
    )

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
