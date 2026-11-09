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

_DIVISIONS = ("East", "North", "South", "West")


@st.composite
def _team_result(draw: st.DrawFn, name: str, conference: str, division: str) -> dict:
    seed_probs = {
        str(s): draw(st.floats(min_value=0, max_value=100, allow_nan=False))
        for s in range(1, 8)
    }
    return {
        "team": name,
        "conference": conference,
        "division": division,
        "playoff_probability": draw(st.floats(min_value=0, max_value=100, allow_nan=False)),
        "seed_probabilities": seed_probs,
    }


@st.composite
def conference_team_results(draw: st.DrawFn) -> list[dict]:
    """A full conference: 16 teams, 4 per division."""
    names = draw(
        st.lists(st.text(min_size=1, max_size=8), min_size=16, max_size=16, unique=True)
    )
    return [
        draw(_team_result(name, "AFC", _DIVISIONS[i // 4]))
        for i, name in enumerate(names)
    ]


def _title_probability(team_result: dict) -> float:
    return sum(team_result["seed_probabilities"][str(s)] for s in range(1, 5))


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
def test_assign_modal_seeds_assigns_exactly_seven(team_results: list[dict]) -> None:
    assigned = assign_modal_seeds(team_results, "AFC")
    assert len(assigned) == 7


@given(conference_team_results())
@settings(max_examples=200)
def test_assign_modal_seeds_division_winners_hold_seeds_1_to_4(team_results: list[dict]) -> None:
    assigned = assign_modal_seeds(team_results, "AFC")
    by_name = {t["team"]: t for t in team_results}
    winners = [by_name[name] for name, seed in assigned.items() if seed <= 4]

    assert sorted(t["division"] for t in winners) == sorted(_DIVISIONS)
    for winner in winners:
        rivals = [t for t in team_results if t["division"] == winner["division"]]
        assert _title_probability(winner) == max(_title_probability(t) for t in rivals)


@given(conference_team_results())
@settings(max_examples=200)
def test_assign_modal_seeds_wild_cards_are_best_remaining(team_results: list[dict]) -> None:
    assigned = assign_modal_seeds(team_results, "AFC")
    wild_cards = [t for t in team_results if assigned.get(t["team"], 0) >= 5]
    left_out = [t for t in team_results if t["team"] not in assigned]

    assert len(wild_cards) == 3
    lowest_wild_card = min(t["playoff_probability"] for t in wild_cards)
    assert all(t["playoff_probability"] <= lowest_wild_card for t in left_out)


def test_assign_modal_seeds_runner_up_cannot_take_division_winner_seed() -> None:
    """Regression for issue #52, using the AFC numbers from that report: the
    Patriots, last to pick, were left with seed 3 despite the Bills winning
    the AFC East, and the AFC West got no division winner at all."""
    rows = [
        ("Jaguars", "South", 97.1, (13.5, 20.6, 24.9, 36.1, 0.3, 0.7, 1.1)),
        ("Bills", "East", 96.9, (30.6, 21.7, 18.8, 14.8, 3.4, 4.0, 3.6)),
        ("Broncos", "West", 95.7, (24.0, 18.0, 13.9, 6.7, 19.3, 8.9, 4.9)),
        ("Steelers", "North", 91.0, (13.3, 16.8, 16.4, 11.3, 11.5, 13.1, 8.6)),
        ("Chiefs", "West", 90.5, (11.5, 9.9, 8.9, 6.1, 27.4, 16.3, 10.3)),
        ("Bengals", "North", 82.4, (5.7, 8.5, 9.2, 7.4, 18.2, 18.9, 14.5)),
        ("Patriots", "East", 60.4, (1.1, 2.4, 3.5, 7.0, 10.6, 15.4, 20.4)),
        ("Browns", "North", 51.7, (0.4, 1.7, 3.3, 4.7, 7.3, 15.1, 19.3)),
    ]
    team_results = [
        {
            "team": name,
            "conference": "AFC",
            "division": division,
            "playoff_probability": playoff,
            "seed_probabilities": {str(s + 1): p for s, p in enumerate(seeds)},
        }
        for name, division, playoff, seeds in rows
    ]

    assert assign_modal_seeds(team_results, "AFC") == {
        "Bills": 1,
        "Broncos": 2,
        "Steelers": 3,
        "Jaguars": 4,
        "Chiefs": 5,
        "Bengals": 6,
        "Patriots": 7,
    }


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
            "division": _DIVISIONS[i // 4],
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
