"""Tests for solver timing storage in the Cache class.

These tests verify the solver_timing table and associated methods:
- store_solver_timing() — inserts timing records with UTC timestamps
- get_solver_timings() — retrieves records ordered by most recent first
- Rolling window pruning — only the 50 most recent records are retained
"""

from __future__ import annotations

from datetime import datetime, UTC

from src.cache import Cache


def test_store_and_retrieve_single_timing() -> None:
    """Store one timing record and retrieve it, verifying all fields match."""
    cache = Cache(":memory:")

    cache.store_solver_timing(
        ms_per_eval=1.5,
        method="enumeration",
        relevant_games_count=12,
        total_evals=50000,
    )

    timings = cache.get_solver_timings()
    assert len(timings) == 1

    record = timings[0]
    assert record["ms_per_eval"] == 1.5
    assert record["method"] == "enumeration"
    assert record["relevant_games_count"] == 12
    assert record["total_evals"] == 50000
    assert "recorded_at" in record


def test_rolling_window_prunes_beyond_50() -> None:
    """Store 55 records and verify only 50 are retained in the table."""
    cache = Cache(":memory:")

    for i in range(55):
        cache.store_solver_timing(
            ms_per_eval=float(i),
            method="sampling",
            relevant_games_count=10,
            total_evals=1000,
        )

    timings = cache.get_solver_timings()
    assert len(timings) == 50


def test_get_solver_timings_returns_most_recent_first() -> None:
    """Verify timings are returned in descending order by recorded_at."""
    cache = Cache(":memory:")

    for i in range(5):
        cache.store_solver_timing(
            ms_per_eval=float(i),
            method="enumeration",
            relevant_games_count=10,
            total_evals=1000,
        )

    timings = cache.get_solver_timings()
    # Most recent record has ms_per_eval=4.0 (last inserted)
    assert timings[0]["ms_per_eval"] == 4.0
    assert timings[-1]["ms_per_eval"] == 0.0

    # Verify descending order by recorded_at
    for j in range(len(timings) - 1):
        assert timings[j]["recorded_at"] >= timings[j + 1]["recorded_at"]


def test_get_solver_timings_empty_table() -> None:
    """Verify empty list is returned when no timing data exists."""
    cache = Cache(":memory:")

    timings = cache.get_solver_timings()
    assert timings == []


def test_store_solver_timing_records_utc_timestamp() -> None:
    """Verify that stored records have an ISO-8601 UTC timestamp."""
    cache = Cache(":memory:")

    before = datetime.now(UTC)
    cache.store_solver_timing(
        ms_per_eval=2.0,
        method="sampling",
        relevant_games_count=8,
        total_evals=2000,
    )
    after = datetime.now(UTC)

    timings = cache.get_solver_timings()
    assert len(timings) == 1

    recorded_at = timings[0]["recorded_at"]
    # Verify it's a valid ISO-8601 string parseable as a datetime
    parsed = datetime.fromisoformat(recorded_at)
    # Should be between before and after
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    assert before <= parsed <= after
