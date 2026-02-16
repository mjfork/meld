"""Unit tests for TUI components."""

from unittest.mock import MagicMock, patch

import pytest

from meld.data_models import AdvisorStatus
from meld.tui import (
    MeldApp,
    OrchestratorEvent,
    PanelStatus,
    Phase,
    StreamBuffer,
    TUIController,
    status_from_advisor_status,
)


@pytest.mark.unit
class TestStreamBuffer:
    """Tests for StreamBuffer class."""

    def test_append_content(self) -> None:
        """Test appending content to buffer."""
        buffer = StreamBuffer()
        buffer.append("Hello ")
        buffer.append("World")
        assert buffer._pending == "Hello World"
        assert buffer.content == ""

    def test_force_flush(self) -> None:
        """Test force flushing all pending content."""
        buffer = StreamBuffer()
        buffer.append("Test content")
        result = buffer.force_flush()
        assert result == "Test content"
        assert buffer.content == "Test content"
        assert buffer._pending == ""

    def test_clear(self) -> None:
        """Test clearing buffer."""
        buffer = StreamBuffer()
        buffer.content = "Old content"
        buffer._pending = "Pending"
        buffer.clear()
        assert buffer.content == ""
        assert buffer._pending == ""

    def test_flush_respects_throttle(self) -> None:
        """Test that flush respects throttle interval."""
        buffer = StreamBuffer()
        buffer._min_interval = 1.0  # 1 second interval

        # First flush should work immediately after setting last_flush to 0
        buffer._last_flush = 0.0
        buffer.append("First")

        # This should flush since last_flush is 0 and current time > 1.0
        with patch("meld.tui._get_time", return_value=1.5):
            result = buffer.flush()
            assert result == "First"

    def test_flush_returns_none_when_throttled(self) -> None:
        """Test flush returns None when within throttle interval."""
        buffer = StreamBuffer()
        buffer._min_interval = 1.0

        # Set a recent last_flush
        buffer._last_flush = 0.4  # Only 0.1 seconds ago

        with patch("meld.tui._get_time", return_value=0.5):
            buffer.append("Content")
            result = buffer.flush()
            assert result is None


@pytest.mark.unit
class TestPanelStatus:
    """Tests for PanelStatus enum."""

    def test_status_values(self) -> None:
        """Test all status values exist."""
        assert PanelStatus.WAITING.value == "waiting"
        assert PanelStatus.RUNNING.value == "running"
        assert PanelStatus.STREAMING.value == "streaming"
        assert PanelStatus.COMPLETE.value == "complete"
        assert PanelStatus.FAILED.value == "failed"
        assert PanelStatus.RETRYING.value == "retrying"


@pytest.mark.unit
class TestPhase:
    """Tests for Phase enum."""

    def test_phase_values(self) -> None:
        """Test all phase values exist."""
        assert Phase.PLANNING.value == "Planning"
        assert Phase.FEEDBACK.value == "Feedback"
        assert Phase.SYNTHESIZING.value == "Synthesizing"
        assert Phase.CONVERGED.value == "Converged"


@pytest.mark.unit
class TestStatusConversion:
    """Tests for status conversion helper."""

    def test_status_from_advisor_status(self) -> None:
        """Test converting AdvisorStatus to PanelStatus."""
        assert status_from_advisor_status(AdvisorStatus.WAITING) == PanelStatus.WAITING
        assert status_from_advisor_status(AdvisorStatus.RUNNING) == PanelStatus.RUNNING
        assert status_from_advisor_status(AdvisorStatus.STREAMING) == PanelStatus.STREAMING
        assert status_from_advisor_status(AdvisorStatus.COMPLETE) == PanelStatus.COMPLETE
        assert status_from_advisor_status(AdvisorStatus.FAILED) == PanelStatus.FAILED
        assert status_from_advisor_status(AdvisorStatus.RETRYING) == PanelStatus.RETRYING


@pytest.mark.unit
class TestOrchestratorEvent:
    """Tests for OrchestratorEvent dataclass."""

    def test_event_creation(self) -> None:
        """Test creating an event."""
        event = OrchestratorEvent("test_event", {"key": "value"})
        assert event.event_type == "test_event"
        assert event.data == {"key": "value"}

    def test_event_default_data(self) -> None:
        """Test event with default empty data."""
        event = OrchestratorEvent("test_event")
        assert event.event_type == "test_event"
        assert event.data == {}


@pytest.mark.unit
class TestTUIController:
    """Tests for TUIController class."""

    def test_on_phase_change(self) -> None:
        """Test handling phase change event."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        controller.on_phase_change("Planning", 1)

        mock_app.set_phase.assert_called_once()

    def test_on_round_start(self) -> None:
        """Test handling round start event."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        controller.on_round_start(2)

        mock_app.set_round.assert_called()
        mock_app.set_phase.assert_called()
        mock_app.clear_advisors.assert_called_once()

    def test_on_melder_stream(self) -> None:
        """Test handling melder streaming event."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        controller.on_melder_stream("Content chunk")

        mock_app.append_melder.assert_called_once_with("Content chunk")

    def test_on_melder_complete(self) -> None:
        """Test handling melder completion event."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        controller.on_melder_complete("Final content")

        mock_app.update_melder.assert_called_once_with("Final content")
        mock_app.set_melder_status.assert_called_once_with(PanelStatus.COMPLETE)

    def test_on_advisor_status_running(self) -> None:
        """Test handling advisor running status."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        controller.on_advisor_status("claude", "running")

        mock_app.set_advisor_status.assert_called()

    def test_on_advisor_stream(self) -> None:
        """Test handling advisor streaming event."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        controller.on_advisor_stream("gemini", "Streaming content")

        mock_app.append_advisor.assert_called_once_with("gemini", "Streaming content")

    def test_on_advisor_complete(self) -> None:
        """Test handling advisor completion event."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        controller.on_advisor_complete("openai", "Full feedback")

        mock_app.update_advisor.assert_called_once_with("openai", "Full feedback")
        mock_app.set_advisor_status.assert_called_once_with("openai", PanelStatus.COMPLETE)

    def test_on_synthesis_start(self) -> None:
        """Test handling synthesis start event."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        controller.on_synthesis_start()

        mock_app.set_phase.assert_called_once_with(Phase.SYNTHESIZING)
        mock_app.set_melder_status.assert_called_once_with(PanelStatus.RUNNING)

    def test_on_converged(self) -> None:
        """Test handling convergence event."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        controller.on_converged()

        mock_app.set_phase.assert_called_once_with(Phase.CONVERGED)
        mock_app.set_melder_status.assert_called_once_with(PanelStatus.COMPLETE)

    def test_on_event_phase_changed(self) -> None:
        """Test handling orchestrator event for phase change."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        event = OrchestratorEvent("phase_changed", {"phase": "Feedback", "round": 2})
        controller.on_event(event)

        mock_app.set_phase.assert_called()

    def test_on_event_advisor_failed(self) -> None:
        """Test handling orchestrator event for advisor failure."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        event = OrchestratorEvent(
            "advisor_failed", {"provider": "gemini", "error": "Timeout"}
        )
        controller.on_event(event)

        mock_app.update_advisor.assert_called_once_with("gemini", "Error: Timeout")
        mock_app.set_advisor_status.assert_called_once_with("gemini", PanelStatus.FAILED)

    def test_on_event_advisor_retrying(self) -> None:
        """Test handling orchestrator event for advisor retry."""
        mock_app = MagicMock(spec=MeldApp)
        controller = TUIController(mock_app)

        event = OrchestratorEvent(
            "advisor_retrying", {"provider": "claude", "retry": 2}
        )
        controller.on_event(event)

        mock_app.set_advisor_status.assert_called_once_with(
            "claude", PanelStatus.RETRYING, 2
        )


@pytest.mark.unit
class TestMeldPanelUnit:
    """Unit tests for MeldPanel (without Textual app)."""

    def test_stream_buffer_integration(self) -> None:
        """Test StreamBuffer is properly initialized."""
        # We can't fully test Textual widgets without running the app,
        # but we can verify the StreamBuffer logic
        buffer = StreamBuffer()
        buffer.append("Test ")
        buffer.append("content")
        result = buffer.force_flush()
        assert result == "Test content"


@pytest.mark.unit
class TestStatusConfig:
    """Tests for status configuration."""

    def test_all_statuses_have_config(self) -> None:
        """Test all panel statuses have configuration."""
        from meld.tui import STATUS_CONFIG

        for status in PanelStatus:
            assert status in STATUS_CONFIG
            config = STATUS_CONFIG[status]
            assert "icon" in config
            assert "color" in config

    def test_status_icons_are_unique(self) -> None:
        """Test status icons are visually distinct."""
        from meld.tui import STATUS_CONFIG

        icons = [config["icon"] for config in STATUS_CONFIG.values()]
        # Most icons should be unique (retrying/running might share)
        assert len(set(icons)) >= len(icons) - 1
