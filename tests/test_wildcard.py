"""Property-based tests for Wild Card Round data assembly (src/wildcard.py).

Covers the two pieces of genuinely new logic this feature adds: modal-seed
assignment for Simulated mode (assign_modal_seeds) and last-5/streak
derivation from a team's game log (last5_and_streak) — plus a structural
check that build_actual_conference/build_simulated_conference always
produce a complete, uniquely-seeded 16-team conference list.
"""

from __future__ import annotations

from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

from src.data_client import Game, GameStatus
from src.standings import Conference, compute_standings
from src.wildcard import (
    assign_modal_seeds,
    build_actual_conference,
    build_simulated_conference,
    last5_and_streak,
)
from tests.strategies.games import completed_game_list


# --- assign_modal_seeds -----------------------------------------------------

@st.composite
def _team_result(draw: st.DrawFn, name: str, conference: str) -> dict:
    seed_probs = {
        str(s): draw(st.floats(min_value=0, max_value=100, allow_nan=False))
        for s in range(1, 8)
    }
    return {
        "team": name,
        "conference": conference,
        "playoff_probability": draw(st.floats(min_value=0, max_value=100, allow_nan=False)),
        "seed_probabilities": seed_probs,
    }


@st.composite
def conference_team_results(draw: st.DrawFn) -> list[dict]:
    names = draw(
        st.lists(st.text(min_size=1, max_size=8), min_size=1, max_size=20, unique=True)
    )
    return [draw(_team_result(name, "AFC")) for name in names]


@given(conference_team_results())
@settings(max_examples=200)
def test_assign_modal_seeds_no_duplicates(team_results: list[dict]) -> None:
    assigned = assign_modal_seeds(team_results, "AFC")
    seeds = list(assigned.values())
    assert len(seeds) == len(set(seeds))


@given(conference_team_results())
@settings(max_examples=200)
def test_assign_modal_seeds_in_range_1_to_7(team_results: list[dict]) -> None:
    assigned = assign_modal_seeds(team_results, "AFC")
    assert all(1 <= s <= 7 for s in assigned.values())


@given(conference_team_results())
@settings(max_examples=200)
def test_assign_modal_seeds_exactly_min_seven_or_fewer(team_results: list[dict]) -> None:
    assigned = assign_modal_seeds(team_results, "AFC")
    assert len(assigned) == min(7, len(team_results))


@given(conference_team_results())
@settings(max_examples=50)
def test_assign_modal_seeds_ignores_other_conference(team_results: list[dict]) -> None:
    for t in team_results:
        t["conference"] = "NFC"
    assert assign_modal_seeds(team_results, "AFC") == {}


# --- last5_and_streak --------------------------------------------------------

def _make_game(week: int, team: str, opponent: str, outcome: str) -> Game:
    if outcome == "W":
        home_score, away_score = 24, 10
    elif outcome == "L":
        home_score, away_score = 10, 24
    else:
        home_score, away_score = 14, 14
    return Game(
        game_id=f"g{week}",
        week=week,
        date=date(2024, 9, 1),
        home_team=team,
        away_team=opponent,
        status=GameStatus.COMPLETED,
        home_score=home_score,
        away_score=away_score,
        home_points=home_score,
        away_points=away_score,
        quarter=None,
        clock=None,
    )


@given(st.lists(st.sampled_from(["W", "L", "T"]), min_size=0, max_size=20))
@settings(max_examples=200)
def test_last5_is_trailing_slice_of_log(outcomes: list[str]) -> None:
    games = [_make_game(i + 1, "Chiefs", "Bills", o) for i, o in enumerate(outcomes)]
    last5, streak = last5_and_streak("Chiefs", games)
    assert last5 == outcomes[-5:]
    assert len(last5) == min(5, len(outcomes))
    if not outcomes:
        assert streak is None


@given(st.lists(st.sampled_from(["W", "L", "T"]), min_size=1, max_size=20))
@settings(max_examples=200)
def test_streak_matches_trailing_run(outcomes: list[str]) -> None:
    games = [_make_game(i + 1, "Chiefs", "Bills", o) for i, o in enumerate(outcomes)]
    _, streak = last5_and_streak("Chiefs", games)
    assert streak is not None
    assert streak.result == outcomes[-1]
    assert 1 <= streak.length <= len(outcomes)

    expected = 0
    for o in reversed(outcomes):
        if o != outcomes[-1]:
            break
        expected += 1
    assert streak.length == expected


def test_last5_and_streak_no_games() -> None:
    assert last5_and_streak("Chiefs", []) == ([], None)


def test_last5_and_streak_ignores_future_and_other_teams() -> None:
    games = [
        _make_game(1, "Chiefs", "Bills", "W"),
        _make_game(2, "Chiefs", "Raiders", "L"),
        Game(
            game_id="g3", week=3, date=date(2024, 9, 1),
            home_team="Chiefs", away_team="Broncos", status=GameStatus.SCHEDULED,
            home_score=None, away_score=None, home_points=None, away_points=None,
            quarter=None, clock=None,
        ),
        _make_game(4, "Bills", "Dolphins", "W"),  # a different team's game
    ]
    last5, streak = last5_and_streak("Chiefs", games)
    assert last5 == ["W", "L"]
    assert streak.result == "L"
    assert streak.length == 1


# --- build_actual_conference / build_simulated_conference -------------------

@given(completed_game_list)
@settings(max_examples=50)
def test_build_actual_conference_seeds_are_1_to_16(games: list[Game]) -> None:
    standings = compute_standings(games)
    result = build_actual_conference(standings, Conference.AFC, games, {}, {})
    assert len(result) == 16
    assert [t["seed"] for t in result] == list(range(1, 17))
    assert len(result) == len({t["team"] for t in result})


@given(completed_game_list)
@settings(max_examples=50)
def test_build_actual_conference_last5_at_most_five(games: list[Game]) -> None:
    standings = compute_standings(games)
    result = build_actual_conference(standings, Conference.NFC, games, {}, {})
    assert all(len(t["last5"]) <= 5 for t in result)


def test_build_simulated_conference_seeds_are_1_to_16() -> None:
    afc_teams = [
        "Bills", "Dolphins", "Patriots", "Jets", "Ravens", "Bengals", "Browns",
        "Steelers", "Texans", "Colts", "Jaguars", "Titans", "Chiefs", "Broncos",
        "Chargers", "Raiders",
    ]
    team_results = [
        {
            "team": name,
            "conference": "AFC",
            "division": "East",
            "record": "0-0-0",
            "playoff_probability": 100.0 - i,
            "seed_probabilities": {str(s): (100.0 if s == i % 7 + 1 else 0.0) for s in range(1, 8)},
            "strength_rating": 1.0,
        }
        for i, name in enumerate(afc_teams)
    ]
    result = build_simulated_conference(team_results, "AFC", [])
    assert len(result) == 16
    assert sorted(t["seed"] for t in result) == list(range(1, 17))
    assert all("playoff_pct" in t for t in result)
