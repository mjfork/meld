"""Unit tests for CLI module."""

import io
import sys
from unittest.mock import MagicMock, patch

import pytest

from meld.cli import create_parser, get_task_input


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_creates_parser(self) -> None:
        """Parser is created successfully."""
        parser = create_parser()
        assert parser is not None
        assert parser.prog == "meld"

    def test_parses_positional_task(self) -> None:
        """Positional task argument is parsed."""
        parser = create_parser()
        args = parser.parse_args(["Add authentication"])
        assert args.task == "Add authentication"

    def test_parses_file_flag(self) -> None:
        """--file flag is parsed."""
        parser = create_parser()
        args = parser.parse_args(["--file", "task.txt"])
        assert args.file == "task.txt"

    def test_parses_prd_flag(self) -> None:
        """--prd flag is parsed."""
        parser = create_parser()
        args = parser.parse_args(["--prd", "requirements.md", "task"])
        assert args.prd == "requirements.md"

    def test_parses_rounds_flag(self) -> None:
        """--rounds flag is parsed with default."""
        parser = create_parser()

        # Default
        args = parser.parse_args(["task"])
        assert args.rounds == 5

        # Custom
        args = parser.parse_args(["--rounds", "7", "task"])
        assert args.rounds == 7

    def test_parses_timeout_flag(self) -> None:
        """--timeout flag is parsed with default."""
        parser = create_parser()

        args = parser.parse_args(["task"])
        assert args.timeout == 600

        args = parser.parse_args(["--timeout", "300", "task"])
        assert args.timeout == 300

    def test_parses_output_flag(self) -> None:
        """--output flag is parsed."""
        parser = create_parser()
        args = parser.parse_args(["--output", "plan.md", "task"])
        assert args.output == "plan.md"

    def test_parses_json_output_flag(self) -> None:
        """--json-output flag is parsed."""
        parser = create_parser()
        args = parser.parse_args(["--json-output", "result.json", "task"])
        assert args.json_output == "result.json"

    def test_parses_quiet_flag(self) -> None:
        """--quiet flag is parsed."""
        parser = create_parser()

        args = parser.parse_args(["task"])
        assert args.quiet is False

        args = parser.parse_args(["--quiet", "task"])
        assert args.quiet is True

    def test_parses_verbose_flag(self) -> None:
        """--verbose flag is parsed."""
        parser = create_parser()

        args = parser.parse_args(["task"])
        assert args.verbose is False

        args = parser.parse_args(["--verbose", "task"])
        assert args.verbose is True

    def test_parses_no_save_flag(self) -> None:
        """--no-save flag is parsed."""
        parser = create_parser()

        args = parser.parse_args(["task"])
        assert args.no_save is False

        args = parser.parse_args(["--no-save", "task"])
        assert args.no_save is True

    def test_parses_skip_preflight_flag(self) -> None:
        """--skip-preflight flag is parsed."""
        parser = create_parser()

        args = parser.parse_args(["task"])
        assert args.skip_preflight is False

        args = parser.parse_args(["--skip-preflight", "task"])
        assert args.skip_preflight is True

    def test_parses_resume_flag(self) -> None:
        """--resume flag is parsed."""
        parser = create_parser()
        args = parser.parse_args(["--resume", "20260116-120000-abcd1234", "task"])
        assert args.resume == "20260116-120000-abcd1234"

    def test_parses_run_dir_flag(self) -> None:
        """--run-dir flag is parsed with default."""
        parser = create_parser()

        args = parser.parse_args(["task"])
        assert args.run_dir == ".meld/runs"

        args = parser.parse_args(["--run-dir", "/tmp/runs", "task"])
        assert args.run_dir == "/tmp/runs"

    def test_doctor_command(self) -> None:
        """doctor is parsed as positional task."""
        parser = create_parser()
        args = parser.parse_args(["doctor"])
        # doctor is treated as a task positional, handled specially in main()
        assert args.task == "doctor"


class TestGetTaskInput:
    """Tests for task input handling."""

    def test_returns_positional_task(self) -> None:
        """Returns task from positional argument."""
        args = MagicMock()
        args.task = "Add authentication"
        args.file = None

        result = get_task_input(args)
        assert result == "Add authentication"

    def test_reads_from_file(self, tmp_path) -> None:
        """Reads task from file when --file specified."""
        task_file = tmp_path / "task.txt"
        task_file.write_text("Task from file\n")

        args = MagicMock()
        args.task = None
        args.file = str(task_file)

        result = get_task_input(args)
        assert result == "Task from file"

    def test_reads_from_stdin(self, monkeypatch) -> None:
        """Reads task from stdin when no other input."""
        args = MagicMock()
        args.task = None
        args.file = None

        # Mock stdin
        monkeypatch.setattr(sys, "stdin", io.StringIO("Task from stdin\n"))
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

        result = get_task_input(args)
        assert result == "Task from stdin"

    def test_raises_when_no_input(self, monkeypatch) -> None:
        """Raises ValueError when no input provided."""
        args = MagicMock()
        args.task = None
        args.file = None

        # Mock interactive terminal
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

        with pytest.raises(ValueError, match="No task provided"):
            get_task_input(args)

    def test_prefers_positional_over_file(self, tmp_path) -> None:
        """Positional task takes precedence over file."""
        task_file = tmp_path / "task.txt"
        task_file.write_text("Task from file")

        args = MagicMock()
        args.task = "Positional task"
        args.file = str(task_file)

        result = get_task_input(args)
        assert result == "Positional task"
