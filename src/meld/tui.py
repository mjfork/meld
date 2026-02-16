"""Terminal User Interface for meld using Textual."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from rich.console import RenderableType
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

from meld.data_models import AdvisorStatus


class PanelStatus(Enum):
    """Status of a TUI panel."""

    WAITING = "waiting"
    RUNNING = "running"
    STREAMING = "streaming"
    COMPLETE = "complete"
    FAILED = "failed"
    RETRYING = "retrying"


# Status display configuration
STATUS_CONFIG: dict[PanelStatus, dict[str, str]] = {
    PanelStatus.WAITING: {"icon": "○", "color": "dim white"},
    PanelStatus.RUNNING: {"icon": "◐", "color": "yellow"},
    PanelStatus.STREAMING: {"icon": "▌", "color": "cyan"},
    PanelStatus.COMPLETE: {"icon": "●", "color": "green"},
    PanelStatus.FAILED: {"icon": "✗", "color": "red"},
    PanelStatus.RETRYING: {"icon": "↻", "color": "darkorange"},
}


class Phase(Enum):
    """Current phase of the meld process."""

    PLANNING = "Planning"
    FEEDBACK = "Feedback"
    SYNTHESIZING = "Synthesizing"
    CONVERGED = "Converged"


def _get_time() -> float:
    """Get current time, handling missing event loop gracefully."""
    try:
        loop = asyncio.get_running_loop()
        return loop.time()
    except RuntimeError:
        # No running event loop, use monotonic time
        import time
        return time.monotonic()


@dataclass
class StreamBuffer:
    """Buffer for streaming content with throttling.

    Accumulates content and provides throttled updates to prevent
    render thrashing during rapid streaming.
    """

    content: str = ""
    _pending: str = ""
    _last_flush: float = field(default_factory=lambda: 0.0)
    _min_interval: float = 1.0 / 60.0  # ~60fps max

    def append(self, text: str) -> None:
        """Append text to the pending buffer."""
        self._pending += text

    def flush(self) -> str | None:
        """Flush pending content if enough time has passed.

        Returns the full content if flushed, None otherwise.
        """
        now = _get_time()
        if self._pending and (now - self._last_flush) >= self._min_interval:
            self.content += self._pending
            self._pending = ""
            self._last_flush = now
            return self.content
        return None

    def force_flush(self) -> str:
        """Force flush all pending content."""
        self.content += self._pending
        self._pending = ""
        self._last_flush = _get_time()
        return self.content

    def clear(self) -> None:
        """Clear all content."""
        self.content = ""
        self._pending = ""


class MeldPanel(Static):
    """Panel showing streaming output from a model."""

    DEFAULT_CSS = """
    MeldPanel {
        border: solid $primary;
        padding: 0 1;
        overflow-y: auto;
    }

    MeldPanel.melder {
        height: 60%;
        border-title-color: $accent;
    }

    MeldPanel.advisor {
        height: 100%;
        border-title-color: $secondary;
    }

    MeldPanel.waiting {
        border: dashed $surface;
    }

    MeldPanel.running {
        border: solid yellow;
    }

    MeldPanel.streaming {
        border: solid cyan;
    }

    MeldPanel.complete {
        border: solid green;
    }

    MeldPanel.failed {
        border: solid red;
    }

    MeldPanel.retrying {
        border: solid darkorange;
    }
    """

    status: reactive[PanelStatus] = reactive(PanelStatus.WAITING)
    elapsed: reactive[float] = reactive(0.0)

    def __init__(
        self,
        provider: str,
        is_melder: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize the panel."""
        super().__init__(*args, **kwargs)
        self.provider = provider
        self.is_melder = is_melder
        self._buffer = StreamBuffer()
        self._start_time: datetime | None = None
        self._retry_count = 0
        self._command: str | None = None  # CLI command for display

        # Add class for styling
        self.add_class("melder" if is_melder else "advisor")

    def on_mount(self) -> None:
        """Called when panel is mounted."""
        self._update_title()

    def watch_status(self, new_status: PanelStatus) -> None:
        """React to status changes."""
        # Remove old status classes and add new one
        for s in PanelStatus:
            self.remove_class(s.value)
        self.add_class(new_status.value)
        self._update_title()

    def watch_elapsed(self, new_elapsed: float) -> None:
        """React to elapsed time changes."""
        self._update_title()

    def _update_title(self) -> None:
        """Update the panel border title."""
        config = STATUS_CONFIG[self.status]
        icon = config["icon"]

        # Format elapsed time
        if self.elapsed > 0:
            minutes = int(self.elapsed // 60)
            seconds = int(self.elapsed % 60)
            if minutes > 0:
                time_str = f"{minutes}m {seconds}s"
            else:
                time_str = f"{seconds}s"
        else:
            time_str = ""

        # Build title
        parts = [self.provider.upper()]
        if self.status == PanelStatus.RETRYING and self._retry_count > 0:
            parts.append(f"Retry {self._retry_count}/3")
        if time_str:
            parts.append(time_str)

        title = f"{icon} {' | '.join(parts)}"
        self.border_title = title

    def update_content(self, text: str) -> None:
        """Replace the panel content."""
        self._buffer.content = text
        self._buffer._pending = ""
        self.update(Text(text, no_wrap=False))

    def append_content(self, text: str) -> None:
        """Append streaming content."""
        self._buffer.append(text)
        # Try to flush if throttle allows
        content = self._buffer.flush()
        if content is not None:
            self.update(Text(content, no_wrap=False))

    def force_update(self) -> None:
        """Force update with all pending content."""
        content = self._buffer.force_flush()
        self.update(Text(content, no_wrap=False))

    def set_status(self, status: PanelStatus, retry_count: int = 0) -> None:
        """Set the panel status."""
        self._retry_count = retry_count
        self.status = status
        if status == PanelStatus.RUNNING:
            self._start_time = datetime.utcnow()

    def tick_elapsed(self) -> None:
        """Update elapsed time."""
        if self._start_time:
            delta = datetime.utcnow() - self._start_time
            self.elapsed = delta.total_seconds()

    def clear(self) -> None:
        """Clear panel content."""
        self._buffer.clear()
        self.update("")
        self._start_time = None
        self.elapsed = 0.0
        self._command = None

    def set_command(self, command: str, prompt_max_len: int = 40) -> None:
        """Set the CLI command to display.

        Args:
            command: Full CLI command string
            prompt_max_len: Max length for prompt portion before truncation
        """
        self._command = command

    def render(self) -> RenderableType:
        """Render the panel content."""
        lines: list[Text] = []

        # Show command if set
        if self._command:
            lines.append(Text(f"$ {self._command}", style="dim italic"))
            lines.append(Text(""))  # Blank line separator

        # Show content or waiting message
        if not self._buffer.content and not self._buffer._pending:
            lines.append(Text("Waiting...", style="dim"))
        else:
            lines.append(Text(self._buffer.content + self._buffer._pending, no_wrap=False))

        # Combine all lines
        result = Text()
        for i, line in enumerate(lines):
            if i > 0:
                result.append("\n")
            result.append_text(line)
        return result


class StatusBar(Static):
    """Status bar showing session info."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
    }
    """

    session_time: reactive[float] = reactive(0.0)
    current_round: reactive[int] = reactive(0)
    max_rounds: reactive[int] = reactive(5)
    phase: reactive[Phase] = reactive(Phase.PLANNING)

    def render(self) -> RenderableType:
        """Render the status bar."""
        minutes = int(self.session_time // 60)
        seconds = int(self.session_time % 60)

        status_icon = "◐" if self.phase != Phase.CONVERGED else "●"
        status_word = "Active" if self.phase != Phase.CONVERGED else "Done"

        parts = [
            f"Session: {minutes}m {seconds}s",
            f"Round {self.current_round}/{self.max_rounds}",
            f"{status_icon} {status_word}",
        ]

        return Text(" | ".join(parts), justify="center")


class PhaseHeader(Static):
    """Header showing current phase."""

    DEFAULT_CSS = """
    PhaseHeader {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
        text-style: bold;
    }
    """

    phase: reactive[Phase] = reactive(Phase.PLANNING)
    current_round: reactive[int] = reactive(0)
    max_rounds: reactive[int] = reactive(5)

    def render(self) -> RenderableType:
        """Render the phase header."""
        if self.phase == Phase.FEEDBACK:
            return Text(f"[Feedback Round {self.current_round}/{self.max_rounds}]")
        return Text(f"[{self.phase.value}]")


class AdvisorContainer(Horizontal):
    """Container for the three advisor panels."""

    DEFAULT_CSS = """
    AdvisorContainer {
        height: 40%;
    }

    AdvisorContainer > MeldPanel {
        width: 1fr;
    }
    """


class MeldApp(App[None]):
    """Main Textual application for meld TUI."""

    TITLE = "meld"

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        height: 100%;
    }

    #melder-panel {
        height: 60%;
    }

    #advisor-container {
        height: 40%;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(
        self,
        max_rounds: int = 5,
        on_ready: Callable[["MeldApp"], None] | None = None,
        cli_command: str | None = None,
    ) -> None:
        """Initialize the app."""
        super().__init__()
        self._max_rounds = max_rounds
        self._on_ready = on_ready
        self._cli_command = cli_command
        self._session_start: datetime | None = None
        self._timer_task: asyncio.Task[None] | None = None

        # Panel references (set in compose)
        self._melder_panel: MeldPanel | None = None
        self._advisor_panels: dict[str, MeldPanel] = {}
        self._phase_header: PhaseHeader | None = None
        self._status_bar: StatusBar | None = None

        # Set subtitle to CLI command if provided
        if cli_command:
            self.sub_title = cli_command
        else:
            self.sub_title = "Multi-model Planning Convergence"

    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        yield Header()
        yield PhaseHeader(id="phase-header")

        with Container(id="main-container"):
            yield MeldPanel("Melder", is_melder=True, id="melder-panel")

            with AdvisorContainer(id="advisor-container"):
                yield MeldPanel("Claude", id="claude-panel")
                yield MeldPanel("Gemini", id="gemini-panel")
                yield MeldPanel("Codex", id="codex-panel")

        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        # Store panel references
        self._melder_panel = self.query_one("#melder-panel", MeldPanel)
        self._advisor_panels = {
            "claude": self.query_one("#claude-panel", MeldPanel),
            "gemini": self.query_one("#gemini-panel", MeldPanel),
            "openai": self.query_one("#codex-panel", MeldPanel),
        }
        self._phase_header = self.query_one("#phase-header", PhaseHeader)
        self._status_bar = self.query_one("#status-bar", StatusBar)

        # Set initial values
        self._status_bar.max_rounds = self._max_rounds
        self._phase_header.max_rounds = self._max_rounds

        # Start session timer
        self._session_start = datetime.utcnow()
        self._timer_task = asyncio.create_task(self._update_timers())

        # Notify ready callback
        if self._on_ready:
            self._on_ready(self)

    async def _update_timers(self) -> None:
        """Update elapsed timers periodically."""
        while True:
            await asyncio.sleep(0.1)  # 10fps for timers

            # Update session time
            if self._session_start and self._status_bar:
                delta = datetime.utcnow() - self._session_start
                self._status_bar.session_time = delta.total_seconds()

            # Update panel timers
            if self._melder_panel:
                self._melder_panel.tick_elapsed()
            for panel in self._advisor_panels.values():
                panel.tick_elapsed()

    async def action_quit(self) -> None:
        """Handle quit action."""
        if self._timer_task:
            self._timer_task.cancel()
        self.exit()

    # Public API for orchestrator integration

    def set_phase(self, phase: Phase, round_num: int = 0) -> None:
        """Set the current phase."""
        if self._phase_header:
            self._phase_header.phase = phase
            self._phase_header.current_round = round_num
        if self._status_bar:
            self._status_bar.phase = phase
            self._status_bar.current_round = round_num

    def set_round(self, round_num: int) -> None:
        """Set the current round number."""
        if self._phase_header:
            self._phase_header.current_round = round_num
        if self._status_bar:
            self._status_bar.current_round = round_num

    def update_melder(self, content: str) -> None:
        """Update melder panel content."""
        if self._melder_panel:
            self._melder_panel.update_content(content)

    def append_melder(self, content: str) -> None:
        """Append to melder panel."""
        if self._melder_panel:
            self._melder_panel.append_content(content)

    def set_melder_status(self, status: PanelStatus) -> None:
        """Set melder panel status."""
        if self._melder_panel:
            self._melder_panel.set_status(status)

    def update_advisor(self, provider: str, content: str) -> None:
        """Update advisor panel content."""
        provider_key = provider.lower()
        if provider_key in self._advisor_panels:
            self._advisor_panels[provider_key].update_content(content)

    def append_advisor(self, provider: str, content: str) -> None:
        """Append to advisor panel."""
        provider_key = provider.lower()
        if provider_key in self._advisor_panels:
            self._advisor_panels[provider_key].append_content(content)

    def set_advisor_status(
        self,
        provider: str,
        status: PanelStatus,
        retry_count: int = 0,
    ) -> None:
        """Set advisor panel status."""
        provider_key = provider.lower()
        if provider_key in self._advisor_panels:
            self._advisor_panels[provider_key].set_status(status, retry_count)

    def set_advisor_command(self, provider: str, command: str) -> None:
        """Set the CLI command displayed in an advisor panel."""
        provider_key = provider.lower()
        if provider_key in self._advisor_panels:
            self._advisor_panels[provider_key].set_command(command)

    def clear_advisors(self) -> None:
        """Clear all advisor panels."""
        for panel in self._advisor_panels.values():
            panel.clear()
            panel.set_status(PanelStatus.WAITING)


@dataclass
class OrchestratorEvent:
    """Event from orchestrator for TUI updates."""

    event_type: str
    data: dict[str, Any] = field(default_factory=dict)


class TUIController:
    """Controller bridging orchestrator and TUI.

    Handles event translation and provides callback interface
    for the orchestrator to send updates.
    """

    def __init__(self, app: MeldApp) -> None:
        """Initialize the controller."""
        self._app = app

    def on_event(self, event: OrchestratorEvent) -> None:
        """Handle an orchestrator event."""
        match event.event_type:
            case "phase_changed":
                phase_name = event.data.get("phase", "Planning")
                round_num = event.data.get("round", 0)
                phase = Phase[phase_name.upper()]
                self._app.set_phase(phase, round_num)

            case "round_started":
                round_num = event.data.get("round", 1)
                self._app.set_round(round_num)
                self._app.set_phase(Phase.FEEDBACK, round_num)
                self._app.clear_advisors()

            case "melder_started":
                self._app.set_melder_status(PanelStatus.RUNNING)

            case "melder_streaming":
                content = event.data.get("content", "")
                self._app.append_melder(content)
                self._app.set_melder_status(PanelStatus.STREAMING)

            case "melder_complete":
                content = event.data.get("content", "")
                self._app.update_melder(content)
                self._app.set_melder_status(PanelStatus.COMPLETE)

            case "advisor_started":
                provider = event.data.get("provider", "")
                command_parts = event.data.get("command", [])
                if command_parts:
                    # Format command with truncated prompt
                    formatted_cmd = truncate_command_prompt(command_parts)
                    self._app.set_advisor_command(provider, formatted_cmd)
                self._app.set_advisor_status(provider, PanelStatus.RUNNING)

            case "advisor_streaming":
                provider = event.data.get("provider", "")
                content = event.data.get("content", "")
                self._app.append_advisor(provider, content)
                self._app.set_advisor_status(provider, PanelStatus.STREAMING)

            case "advisor_complete":
                provider = event.data.get("provider", "")
                content = event.data.get("content", "")
                self._app.update_advisor(provider, content)
                self._app.set_advisor_status(provider, PanelStatus.COMPLETE)

            case "advisor_failed":
                provider = event.data.get("provider", "")
                error = event.data.get("error", "Unknown error")
                self._app.update_advisor(provider, f"Error: {error}")
                self._app.set_advisor_status(provider, PanelStatus.FAILED)

            case "advisor_retrying":
                provider = event.data.get("provider", "")
                retry_count = event.data.get("retry", 1)
                self._app.set_advisor_status(
                    provider, PanelStatus.RETRYING, retry_count
                )

            case "synthesis_started":
                self._app.set_phase(Phase.SYNTHESIZING)
                self._app.set_melder_status(PanelStatus.RUNNING)

            case "converged":
                self._app.set_phase(Phase.CONVERGED)
                self._app.set_melder_status(PanelStatus.COMPLETE)

    # Convenience methods for direct orchestrator callbacks

    def on_phase_change(self, phase: str, round_num: int = 0) -> None:
        """Handle phase change."""
        self.on_event(OrchestratorEvent(
            "phase_changed",
            {"phase": phase, "round": round_num},
        ))

    def on_round_start(self, round_num: int) -> None:
        """Handle round start."""
        self.on_event(OrchestratorEvent("round_started", {"round": round_num}))

    def on_melder_stream(self, content: str) -> None:
        """Handle melder streaming content."""
        self.on_event(OrchestratorEvent("melder_streaming", {"content": content}))

    def on_melder_complete(self, content: str) -> None:
        """Handle melder completion."""
        self.on_event(OrchestratorEvent("melder_complete", {"content": content}))

    def on_advisor_status(self, provider: str, status: str) -> None:
        """Handle advisor status change."""
        status_map = {
            "running": "advisor_started",
            "streaming": "advisor_streaming",
            "complete": "advisor_complete",
            "failed": "advisor_failed",
            "retrying": "advisor_retrying",
        }
        event_type = status_map.get(status, "advisor_started")
        self.on_event(OrchestratorEvent(event_type, {"provider": provider}))

    def on_advisor_stream(self, provider: str, content: str) -> None:
        """Handle advisor streaming content."""
        self.on_event(OrchestratorEvent(
            "advisor_streaming",
            {"provider": provider, "content": content},
        ))

    def on_advisor_complete(self, provider: str, content: str) -> None:
        """Handle advisor completion."""
        self.on_event(OrchestratorEvent(
            "advisor_complete",
            {"provider": provider, "content": content},
        ))

    def on_synthesis_start(self) -> None:
        """Handle synthesis start."""
        self.on_event(OrchestratorEvent("synthesis_started"))

    def on_converged(self) -> None:
        """Handle convergence."""
        self.on_event(OrchestratorEvent("converged"))


def truncate_command_prompt(command_parts: list[str], max_prompt_len: int = 40) -> str:
    """Format a command with truncated prompt for display.

    Args:
        command_parts: Command as list of strings (from build_command)
        max_prompt_len: Max length for prompt before truncation

    Returns:
        Formatted command string with truncated prompt
    """
    result_parts: list[str] = []
    for i, part in enumerate(command_parts):
        # Check if this looks like a prompt (long string after -p flag)
        if i > 0 and command_parts[i - 1] == "-p" and len(part) > max_prompt_len:
            truncated = part[:max_prompt_len] + "..."
            # Quote if contains spaces
            if " " in truncated:
                result_parts.append(f'"{truncated}"')
            else:
                result_parts.append(truncated)
        elif " " in part:
            # Quote parts with spaces
            result_parts.append(f'"{part}"')
        else:
            result_parts.append(part)
    return " ".join(result_parts)


def status_from_advisor_status(status: AdvisorStatus) -> PanelStatus:
    """Convert AdvisorStatus to PanelStatus."""
    mapping = {
        AdvisorStatus.WAITING: PanelStatus.WAITING,
        AdvisorStatus.RUNNING: PanelStatus.RUNNING,
        AdvisorStatus.STREAMING: PanelStatus.STREAMING,
        AdvisorStatus.COMPLETE: PanelStatus.COMPLETE,
        AdvisorStatus.FAILED: PanelStatus.FAILED,
        AdvisorStatus.RETRYING: PanelStatus.RETRYING,
    }
    return mapping.get(status, PanelStatus.WAITING)


async def run_with_tui(
    orchestrator_coro: Any,
    max_rounds: int = 5,
) -> Any:
    """Run orchestrator with TUI.

    This is a helper function that runs the orchestrator coroutine
    alongside the TUI app.

    Args:
        orchestrator_coro: The orchestrator coroutine to run
        max_rounds: Maximum rounds for display

    Returns:
        The result from the orchestrator
    """
    result: Any = None
    exception: BaseException | None = None

    async def run_orchestrator(app: MeldApp) -> None:
        nonlocal result, exception
        try:
            result = await orchestrator_coro
        except BaseException as e:
            exception = e
        finally:
            app.exit()

    def on_ready(app: MeldApp) -> None:
        asyncio.create_task(run_orchestrator(app))

    app = MeldApp(max_rounds=max_rounds, on_ready=on_ready)
    await app.run_async()

    if exception:
        raise exception
    return result
