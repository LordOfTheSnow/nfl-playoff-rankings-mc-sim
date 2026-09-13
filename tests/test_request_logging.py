"""Tests for NFLRequestHandler.log_message's polling-noise suppression.

The frontend polls GET /api/simulate/status/{job_id} every ~600ms while a
simulation runs (see CHANGELOG), which would otherwise flood the server log
with an identical, uninformative line every poll tick for however long the
run takes -- log_message skips just that one path pattern.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from src.server import NFLRequestHandler


def _log_message(path: str, format_str: str = "%s", *args) -> None:
    """Call the real (unbound) log_message with a minimal stand-in self,
    avoiding a full socket-backed handler instantiation."""
    fake_self = SimpleNamespace(path=path)
    with patch("src.server.logger") as mock_logger:
        NFLRequestHandler.log_message(fake_self, format_str, *args)
        return mock_logger


class TestLogMessageSuppressesStatusPolling:
    def test_status_poll_requests_are_not_logged(self) -> None:
        mock_logger = _log_message("/api/simulate/status/abc123", '"%s" %s -', "GET /api/simulate/status/abc123 HTTP/1.1", "200")
        mock_logger.info.assert_not_called()

    def test_other_simulate_paths_are_still_logged(self) -> None:
        mock_logger = _log_message("/api/simulate", '"%s" %s -', "POST /api/simulate HTTP/1.1", "202")
        mock_logger.info.assert_called_once()

    def test_cancel_requests_are_still_logged(self) -> None:
        mock_logger = _log_message("/api/simulate/cancel/abc123", '"%s" %s -', "POST /api/simulate/cancel/abc123 HTTP/1.1", "200")
        mock_logger.info.assert_called_once()

    def test_unrelated_requests_are_still_logged(self) -> None:
        mock_logger = _log_message("/api/status", '"%s" %s -', "GET /api/status HTTP/1.1", "200")
        mock_logger.info.assert_called_once()
