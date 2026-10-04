"""Tests for the teaser baseline: extraction from a simulation result and
persistence in the Cache.

The baseline is what week-over-week deltas on the teaser image are measured
against, so it must hold exactly the numbers of one complete run and be
keyed by season.
"""

from __future__ import annotations

import copy

import pytest

from src.cache import Cache
from src.nfl_teams import ALL_TEAMS
from src.teaser import extract_baseline_probabilities


def _simulation_result(**overrides: object) -> dict:
    """A minimal simulation result with a probability for every team."""
    result = {
        "cutoff_week_used": 9,
        "team_results": [
            {"team": team, "playoff_probability": float(i)}
            for i, team in enumerate(ALL_TEAMS)
        ],
    }
    result.update(overrides)
    return result


def test_extract_returns_probability_for_every_team() -> None:
    """A complete result yields one probability per team, keyed by team name."""
    probabilities = extract_baseline_probabilities(_simulation_result())

    assert probabilities is not None
    assert set(probabilities) == set(ALL_TEAMS)
    assert probabilities[ALL_TEAMS[3]] == 3.0


def test_extract_rejects_missing_team() -> None:
    """A partial result cannot become a baseline."""
    result = _simulation_result()
    result["team_results"] = result["team_results"][:-1]

    assert extract_baseline_probabilities(result) is None


def test_extract_rejects_unknown_team() -> None:
    """A team name outside the 32 NFL teams invalidates the payload."""
    result = copy.deepcopy(_simulation_result())
    result["team_results"][0]["team"] = "Not A Team"

    assert extract_baseline_probabilities(result) is None


@pytest.mark.parametrize("bad_value", [None, "50", True, float("nan"), float("inf"), -1.0, 100.5])
def test_extract_rejects_invalid_probability(bad_value: object) -> None:
    """Non-numeric, boolean, non-finite, or out-of-range probabilities are rejected."""
    result = copy.deepcopy(_simulation_result())
    result["team_results"][0]["playoff_probability"] = bad_value

    assert extract_baseline_probabilities(result) is None


@pytest.mark.parametrize("payload", [None, [], "result", {"team_results": None}])
def test_extract_rejects_malformed_payload(payload: object) -> None:
    """Anything other than a dict with a team_results list is rejected."""
    assert extract_baseline_probabilities(payload) is None


def test_store_and_get_round_trip() -> None:
    """A saved baseline comes back with the same cutoff and probabilities."""
    cache = Cache(":memory:")
    probabilities = {team: float(i) for i, team in enumerate(ALL_TEAMS)}

    stored = cache.store_teaser_baseline(2025, 9, probabilities)
    loaded = cache.get_teaser_baseline(2025)

    assert loaded == stored
    assert loaded is not None
    assert loaded["cutoff_week"] == 9
    assert loaded["probabilities"] == probabilities


def test_get_returns_none_when_nothing_saved() -> None:
    """No baseline for a season means None, not an error."""
    cache = Cache(":memory:")

    assert cache.get_teaser_baseline(2025) is None


def test_store_overwrites_previous_baseline_for_same_season() -> None:
    """Saving again replaces the season's baseline rather than adding a second one."""
    cache = Cache(":memory:")
    cache.store_teaser_baseline(2025, 8, {ALL_TEAMS[0]: 10.0})
    cache.store_teaser_baseline(2025, 9, {ALL_TEAMS[0]: 20.0})

    loaded = cache.get_teaser_baseline(2025)

    assert loaded is not None
    assert loaded["cutoff_week"] == 9
    assert loaded["probabilities"] == {ALL_TEAMS[0]: 20.0}


def test_baselines_are_isolated_per_season() -> None:
    """Saving for one season does not touch another season's baseline."""
    cache = Cache(":memory:")
    cache.store_teaser_baseline(2024, 5, {ALL_TEAMS[0]: 1.0})
    cache.store_teaser_baseline(2025, 9, {ALL_TEAMS[0]: 2.0})

    loaded_2024 = cache.get_teaser_baseline(2024)

    assert loaded_2024 is not None
    assert loaded_2024["probabilities"] == {ALL_TEAMS[0]: 1.0}
    assert cache.get_teaser_baseline(2023) is None
