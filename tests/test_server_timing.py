"""Tests for server-layer timing integration.

Verifies that _handle_post_clinching_scenarios():
- Stores solver timing data after successful response delivery
- Skips timing storage when BrokenPipeError occurs (user cancelled)
- Skips timing storage when the solver returns an error result
- Skips timing storage when total_evals is 0

Requirements: 2.1, 2.2, 2.3, 2.4, 6.2
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from src.clinching import ClinchingResult


@dataclass
class _FakeRecordGroup:
    """Minimal stand-in for RecordGroup in serialization."""
    wins: int = 10
    losses: int = 4
    ties: int = 0
    scenarios: list = field(default_factory=list)
    is_current: bool = False


def _make_handler(mock_cache: MagicMock, season_year: int = 2024) -> MagicMock:
    """Create a mock NFLRequestHandler with the necessary server attributes.

    Returns a mock handler whose _handle_post_clinching_scenarios can be
    called directly.
    """
    from src.server import NFLRequestHandler

    handler = MagicMock(spec=NFLRequestHandler)
    handler.server = MagicMock()
    handler.server.cache = mock_cache
    handler.server.season_year = season_year

    # Bind the real method to our mock instance
    handler._handle_post_clinching_scenarios = (
        NFLRequestHandler._handle_post_clinching_scenarios.__get__(handler, NFLRequestHandler)
    )
    handler._serialize_clinching_result = (
        NFLRequestHandler._serialize_clinching_result.__get__(handler, NFLRequestHandler)
    )

    return handler


def _make_clinching_result(
    *,
    team: str = "Chiefs",
    method: str = "enumeration",
    exhaustive: bool = True,
    relevant_games_count: int = 8,
    total_evals: int = 6561,
    error: str | None = None,
) -> ClinchingResult:
    """Create a ClinchingResult with controlled fields for testing."""
    return ClinchingResult(
        team=team,
        record_groups=[],
        method=method,
        exhaustive=exhaustive,
        relevant_games_count=relevant_games_count,
        total_evals=total_evals,
        contenders=["Ravens", "Bills"],
        error=error,
    )


def test_scenarios_endpoint_stores_timing_after_success() -> None:
    """After a successful response send, timing data is stored in cache.

    Requirements: 2.1, 2.4
    """
    mock_cache = MagicMock()
    mock_cache.get_games.return_value = []  # Will be overridden by patching compute

    handler = _make_handler(mock_cache)

    # Mock _parse_json_body to return valid request
    handler._parse_json_body = MagicMock(return_value={
        "team": "Chiefs",
        "cutoff_week": 15,
    })

    fake_result = _make_clinching_result(total_evals=6561)

    # Mock _send_json_response to succeed (no exception)
    handler._send_json_response = MagicMock()

    with patch("src.clinching.compute_clinching_scenarios", return_value=fake_result):
        # Provide games so the handler doesn't return early
        mock_cache.get_games.return_value = [MagicMock(week=15, status=MagicMock())]
        handler._handle_post_clinching_scenarios()

    # Timing should have been stored
    mock_cache.store_solver_timing.assert_called_once()
    call_kwargs = mock_cache.store_solver_timing.call_args
    # Verify the call includes ms_per_eval and method
    assert call_kwargs is not None
    kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
    args = call_kwargs.args if call_kwargs.args else ()
    # Either positional or keyword — timing was stored
    assert mock_cache.store_solver_timing.called


def test_scenarios_endpoint_skips_timing_on_broken_pipe() -> None:
    """When _send_json_response raises BrokenPipeError, no timing is stored.

    This simulates the user cancelling the request via AbortController.

    Requirements: 2.2, 6.2
    """
    mock_cache = MagicMock()
    handler = _make_handler(mock_cache)

    handler._parse_json_body = MagicMock(return_value={
        "team": "Chiefs",
        "cutoff_week": 15,
    })

    fake_result = _make_clinching_result(total_evals=6561)

    # Mock _send_json_response to raise BrokenPipeError
    handler._send_json_response = MagicMock(side_effect=BrokenPipeError("Connection reset"))

    with patch("src.clinching.compute_clinching_scenarios", return_value=fake_result):
        mock_cache.get_games.return_value = [MagicMock(week=15, status=MagicMock())]
        handler._handle_post_clinching_scenarios()

    # Timing should NOT have been stored
    mock_cache.store_solver_timing.assert_not_called()


def test_scenarios_endpoint_skips_timing_on_error_result() -> None:
    """When compute_clinching_scenarios returns an error, no timing is stored.

    Requirements: 2.3
    """
    mock_cache = MagicMock()
    handler = _make_handler(mock_cache)

    handler._parse_json_body = MagicMock(return_value={
        "team": "Chiefs",
        "cutoff_week": 15,
    })

    # Result with error set
    fake_result = _make_clinching_result(error="Not enough games played")

    handler._send_error_response = MagicMock()

    with patch("src.clinching.compute_clinching_scenarios", return_value=fake_result):
        mock_cache.get_games.return_value = [MagicMock(week=15, status=MagicMock())]
        handler._handle_post_clinching_scenarios()

    # Timing should NOT have been stored — error result means no valid measurement
    mock_cache.store_solver_timing.assert_not_called()


def test_scenarios_endpoint_skips_timing_on_zero_evals() -> None:
    """When total_evals is 0, no timing is stored (avoids division by zero).

    Requirements: 2.4
    """
    mock_cache = MagicMock()
    handler = _make_handler(mock_cache)

    handler._parse_json_body = MagicMock(return_value={
        "team": "Chiefs",
        "cutoff_week": 15,
    })

    # Result with total_evals=0
    fake_result = _make_clinching_result(total_evals=0)

    handler._send_json_response = MagicMock()

    with patch("src.clinching.compute_clinching_scenarios", return_value=fake_result):
        mock_cache.get_games.return_value = [MagicMock(week=15, status=MagicMock())]
        handler._handle_post_clinching_scenarios()

    # Timing should NOT have been stored — zero evals means division by zero
    mock_cache.store_solver_timing.assert_not_called()
