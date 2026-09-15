"""Tests for "impact games" computation (Simulator._compute_all_impact_games).

For each team, this ranks the top 5 remaining games by how much forcing a
win vs. a loss in that game would move the team's playoff probability. It
was previously untested and the dominant cost of a simulation request (see
CHANGELOG) -- these tests cover the two behavior changes made to cut that
cost: skipping teams whose main-simulation result is already unanimous
(0% or 100%), and dispatching parallel work per (team, game) pair instead
of per team.
"""

from __future__ import annotations

import random
from datetime import date

from src.data_client import Game, GameStatus
from src.nfl_teams import NFL_TEAMS
from src.simulator import (
    SimulationConfig,
    Simulator,
    TeamResult,
    _compute_game_impact_worker,
)


def _make_completed_game(game_id: str, week: int, home: str, away: str, home_score: int, away_score: int) -> Game:
    return Game(
        game_id=game_id, week=week, date=date(2025, 9, 7),
        home_team=home, away_team=away, status=GameStatus.COMPLETED,
        home_score=home_score, away_score=away_score,
        home_points=home_score, away_points=away_score,
        quarter=None, clock=None,
    )


def _make_scheduled_game(game_id: str, week: int, home: str, away: str) -> Game:
    return Game(
        game_id=game_id, week=week, date=date(2025, 12, 21),
        home_team=home, away_team=away, status=GameStatus.SCHEDULED,
        home_score=None, away_score=None, home_points=None, away_points=None,
        quarter=None, clock=None,
    )


def _build_minimal_season() -> list[Game]:
    """A minimal but complete 32-team season: weeks 1-14 decided (in-division
    pairings), weeks 15-18 remaining -- mirrors test_parallel_simulation.py's
    builder so the real standings/tiebreaker engine has a full league to work
    with."""
    games: list[Game] = []
    game_counter = 0

    for week in range(1, 15):
        for divisions in NFL_TEAMS.values():
            for teams in divisions.values():
                for home, away in [(teams[0], teams[1]), (teams[2], teams[3])]:
                    game_counter += 1
                    random.seed(game_counter * 100 + week)
                    games.append(_make_completed_game(
                        f"game_{game_counter}", week, home, away,
                        random.randint(10, 35), random.randint(10, 35),
                    ))

    for week in range(15, 19):
        for divisions in NFL_TEAMS.values():
            for teams in divisions.values():
                for home, away in [(teams[0], teams[3]), (teams[1], teams[2])]:
                    game_counter += 1
                    games.append(_make_scheduled_game(f"game_{game_counter}", week, home, away))

    return games


def _team_results_stub(strengths: dict[str, float], probability_overrides: dict[str, float] | None = None) -> dict[str, TeamResult]:
    overrides = probability_overrides or {}
    return {
        team: TeamResult(
            team=team,
            conference="AFC",
            division="AFC East",
            playoff_probability=overrides.get(team, 0.5),
            seed_distribution={},
            division_champion_probability=0.0,
            strength_rating=strengths.get(team, 1.0),
        )
        for team in strengths
    }


class TestComputeTeamImpact:
    def test_returns_at_most_five_sorted_descending(self) -> None:
        all_games = _build_minimal_season()
        games_to_simulate = [g for g in all_games if g.status == GameStatus.SCHEDULED]
        strengths = {team: 1.0 for divisions in NFL_TEAMS.values() for teams in divisions.values() for team in teams}

        sim = Simulator(SimulationConfig(iterations=100, tie_probability=0.03, noise=0.3, num_workers=1))
        team = next(iter(strengths))
        scores = sim._compute_team_impact(team, all_games, games_to_simulate, strengths, impact_iterations=3)

        assert len(scores) <= 5
        impacts = [impact for _, impact in scores]
        assert impacts == sorted(impacts, reverse=True)
        assert all(0.0 <= impact <= 1.0 for impact in impacts)
        game_ids = {g.game_id for g in games_to_simulate if g.home_team == team or g.away_team == team}
        assert all(game_id in game_ids for game_id, _ in scores)


class TestComputeAllImpactGamesSkipsDecidedTeams:
    def test_unanimous_teams_get_no_impact_games(self) -> None:
        all_games = _build_minimal_season()
        games_to_simulate = [g for g in all_games if g.status == GameStatus.SCHEDULED]
        fixed_games = [g for g in all_games if g.status == GameStatus.COMPLETED]
        strengths = {team: 1.0 for divisions in NFL_TEAMS.values() for teams in divisions.values() for team in teams}
        teams = list(strengths)

        # First team is a lock (100%), second is eliminated (0%), rest at 50%.
        overrides = {teams[0]: 1.0, teams[1]: 0.0}
        team_results = _team_results_stub(strengths, overrides)

        sim = Simulator(SimulationConfig(iterations=100, tie_probability=0.03, noise=0.3, num_workers=1))
        sim._compute_all_impact_games(
            team_results, all_games, games_to_simulate, fixed_games, strengths,
            iterations=3, num_workers=1,
        )

        assert team_results[teams[0]].impact_games == []
        assert team_results[teams[1]].impact_games == []
        # A team without a unanimous result still gets analyzed.
        assert team_results[teams[2]].impact_games != []


class TestComputeAllImpactGamesParallelMatchesSequentialShape:
    def test_parallel_dispatch_populates_same_teams_as_sequential(self) -> None:
        all_games = _build_minimal_season()
        games_to_simulate = [g for g in all_games if g.status == GameStatus.SCHEDULED]
        fixed_games = [g for g in all_games if g.status == GameStatus.COMPLETED]
        strengths = {team: 1.0 for divisions in NFL_TEAMS.values() for teams in divisions.values() for team in teams}
        teams = list(strengths)[:4]  # keep the test fast
        overrides = {t: 0.5 for t in teams}

        seq_results = _team_results_stub(strengths, overrides)
        par_results = _team_results_stub(strengths, overrides)

        sim = Simulator(SimulationConfig(iterations=100, tie_probability=0.03, noise=0.3, num_workers=1))

        # Restrict to a handful of teams by only passing their games through
        # games_to_simulate's team membership check indirectly: just assert
        # on the subset we overrode, ignoring the rest of the league.
        sim._compute_all_impact_games(
            seq_results, all_games, games_to_simulate, fixed_games, strengths,
            iterations=3, num_workers=1,
        )
        sim._compute_all_impact_games(
            par_results, all_games, games_to_simulate, fixed_games, strengths,
            iterations=3, num_workers=2,
        )

        for team in teams:
            assert len(seq_results[team].impact_games) <= 5
            assert len(par_results[team].impact_games) <= 5
            assert len(seq_results[team].impact_games) > 0
            assert len(par_results[team].impact_games) > 0


class TestComputeGameImpactWorker:
    def test_returns_team_game_id_and_bounded_impact(self) -> None:
        all_games = _build_minimal_season()
        games_to_simulate = [g for g in all_games if g.status == GameStatus.SCHEDULED]
        strengths = {team: 1.0 for divisions in NFL_TEAMS.values() for teams in divisions.values() for team in teams}
        team = next(iter(strengths))
        game = next(g for g in games_to_simulate if g.home_team == team or g.away_team == team)

        args = (team, game, all_games, games_to_simulate, strengths, 3, 0.03, 0.3)
        result_team, game_id, impact = _compute_game_impact_worker(args)

        assert result_team == team
        assert game_id == game.game_id
        assert 0.0 <= impact <= 1.0
