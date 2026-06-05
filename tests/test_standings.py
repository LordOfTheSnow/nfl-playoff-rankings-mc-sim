"""Unit tests for NFL standings computation.

Tests the core standings logic: W-L-T records, win percentage,
games behind, division/conference records, simulated outcomes,
and playoff bracket construction.
"""

from datetime import date

import pytest

from src.data_client import Game, GameStatus
from src.nfl_teams import NFL_TEAMS
from src.standings import (
    Conference,
    Division,
    PlayoffBracket,
    TeamStanding,
    WildCardMatchup,
    _calculate_games_behind,
    _calculate_win_percentage,
    _sort_teams_by_record,
    compute_standings,
    determine_playoff_bracket,
    get_wild_card_matchups,
)


class TestWinPercentage:
    """Tests for win percentage calculation."""

    def test_perfect_record(self) -> None:
        assert _calculate_win_percentage(17, 0, 0) == 1.0

    def test_winless_record(self) -> None:
        assert _calculate_win_percentage(0, 17, 0) == 0.0

    def test_zero_games(self) -> None:
        """Division by zero case: 0 games played returns 0.0."""
        assert _calculate_win_percentage(0, 0, 0) == 0.0

    def test_ties_count_half(self) -> None:
        # (10 + 0.5*2) / (10+5+2) = 11/17
        result = _calculate_win_percentage(10, 5, 2)
        assert result == pytest.approx(11 / 17)

    def test_all_ties(self) -> None:
        # (0 + 0.5*17) / 17 = 0.5
        assert _calculate_win_percentage(0, 0, 17) == 0.5

    def test_even_record(self) -> None:
        # (8 + 0) / 16 = 0.5
        assert _calculate_win_percentage(8, 8, 0) == 0.5


class TestGamesBehind:
    """Tests for games behind calculation."""

    def test_leader_is_zero(self) -> None:
        assert _calculate_games_behind(10, 3, 10, 3) == 0.0

    def test_one_game_behind(self) -> None:
        # ((10-9) + (4-3)) / 2 = 1.0
        assert _calculate_games_behind(10, 3, 9, 4) == 1.0

    def test_two_games_behind(self) -> None:
        # ((10-8) + (5-3)) / 2 = 2.0
        assert _calculate_games_behind(10, 3, 8, 5) == 2.0

    def test_half_game_behind(self) -> None:
        # ((10-10) + (4-3)) / 2 = 0.5
        assert _calculate_games_behind(10, 3, 10, 4) == 0.5

    def test_negative_games_behind_not_possible_for_leader(self) -> None:
        # Leader always has 0 GB
        assert _calculate_games_behind(10, 3, 10, 3) == 0.0


class TestComputeStandings:
    """Tests for the main compute_standings function."""

    def test_returns_32_teams(self) -> None:
        """Should always return exactly 32 team standings."""
        standings = compute_standings([])
        assert len(standings) == 32

    def test_all_teams_present(self) -> None:
        """All 32 NFL teams should be represented."""
        from src.nfl_teams import ALL_TEAMS

        standings = compute_standings([])
        team_names = {s.team for s in standings}
        assert team_names == set(ALL_TEAMS)

    def test_empty_games_all_zeros(self) -> None:
        """With no games, all records should be 0-0-0."""
        standings = compute_standings([])
        for s in standings:
            assert s.wins == 0
            assert s.losses == 0
            assert s.ties == 0
            assert s.win_percentage == 0.0
            assert s.games_behind == 0.0
            assert s.points_for is None
            assert s.points_against is None

    def test_completed_game_updates_records(self) -> None:
        """A completed game should update W-L records."""
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Ravens",
                status=GameStatus.COMPLETED,
                home_score=27, away_score=20,
                home_points=27, away_points=20,
                quarter=None, clock=None,
            ),
        ]
        standings = compute_standings(games)
        chiefs = next(s for s in standings if s.team == "Chiefs")
        ravens = next(s for s in standings if s.team == "Ravens")

        assert chiefs.wins == 1
        assert chiefs.losses == 0
        assert ravens.wins == 0
        assert ravens.losses == 1

    def test_tie_game_updates_records(self) -> None:
        """A tied game should update tie counts for both teams."""
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Broncos",
                status=GameStatus.COMPLETED,
                home_score=24, away_score=24,
                home_points=24, away_points=24,
                quarter=None, clock=None,
            ),
        ]
        standings = compute_standings(games)
        chiefs = next(s for s in standings if s.team == "Chiefs")
        broncos = next(s for s in standings if s.team == "Broncos")

        assert chiefs.ties == 1
        assert broncos.ties == 1
        assert chiefs.win_percentage == 0.5
        assert broncos.win_percentage == 0.5

    def test_points_from_completed_games_only(self) -> None:
        """Points should only come from completed games."""
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Ravens",
                status=GameStatus.COMPLETED,
                home_score=27, away_score=20,
                home_points=27, away_points=20,
                quarter=None, clock=None,
            ),
        ]
        standings = compute_standings(games)
        chiefs = next(s for s in standings if s.team == "Chiefs")
        assert chiefs.points_for == 27
        assert chiefs.points_against == 20

    def test_scheduled_games_ignored(self) -> None:
        """Scheduled games should not affect records."""
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Ravens",
                status=GameStatus.SCHEDULED,
                home_score=None, away_score=None,
                home_points=None, away_points=None,
                quarter=None, clock=None,
            ),
        ]
        standings = compute_standings(games)
        chiefs = next(s for s in standings if s.team == "Chiefs")
        assert chiefs.wins == 0
        assert chiefs.losses == 0
        assert chiefs.ties == 0

    def test_division_record_same_division(self) -> None:
        """Games between teams in the same division update division record."""
        # Chiefs and Broncos are both AFC West
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Broncos",
                status=GameStatus.COMPLETED,
                home_score=27, away_score=20,
                home_points=27, away_points=20,
                quarter=None, clock=None,
            ),
        ]
        standings = compute_standings(games)
        chiefs = next(s for s in standings if s.team == "Chiefs")
        broncos = next(s for s in standings if s.team == "Broncos")

        assert chiefs.division_record == (1, 0, 0)
        assert broncos.division_record == (0, 1, 0)

    def test_division_record_different_division(self) -> None:
        """Games between teams in different divisions don't update division record."""
        # Chiefs (AFC West) vs Ravens (AFC North)
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Ravens",
                status=GameStatus.COMPLETED,
                home_score=27, away_score=20,
                home_points=27, away_points=20,
                quarter=None, clock=None,
            ),
        ]
        standings = compute_standings(games)
        chiefs = next(s for s in standings if s.team == "Chiefs")
        assert chiefs.division_record == (0, 0, 0)

    def test_conference_record_same_conference(self) -> None:
        """Games between teams in the same conference update conference record."""
        # Chiefs (AFC West) vs Ravens (AFC North) — same conference
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Ravens",
                status=GameStatus.COMPLETED,
                home_score=27, away_score=20,
                home_points=27, away_points=20,
                quarter=None, clock=None,
            ),
        ]
        standings = compute_standings(games)
        chiefs = next(s for s in standings if s.team == "Chiefs")
        ravens = next(s for s in standings if s.team == "Ravens")

        assert chiefs.conference_record == (1, 0, 0)
        assert ravens.conference_record == (0, 1, 0)

    def test_conference_record_different_conference(self) -> None:
        """Games between teams in different conferences don't update conference record."""
        # Chiefs (AFC) vs Eagles (NFC)
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Eagles",
                status=GameStatus.COMPLETED,
                home_score=27, away_score=20,
                home_points=27, away_points=20,
                quarter=None, clock=None,
            ),
        ]
        standings = compute_standings(games)
        chiefs = next(s for s in standings if s.team == "Chiefs")
        eagles = next(s for s in standings if s.team == "Eagles")

        assert chiefs.conference_record == (0, 0, 0)
        assert eagles.conference_record == (0, 0, 0)

    def test_games_behind_within_division(self) -> None:
        """Games behind should be calculated relative to division leader."""
        # Chiefs beat Broncos twice — Chiefs lead AFC West
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Broncos",
                status=GameStatus.COMPLETED,
                home_score=27, away_score=20,
                home_points=27, away_points=20,
                quarter=None, clock=None,
            ),
            Game(
                game_id="g2", week=2, date=date(2024, 9, 12),
                home_team="Chiefs", away_team="Raiders",
                status=GameStatus.COMPLETED,
                home_score=30, away_score=14,
                home_points=30, away_points=14,
                quarter=None, clock=None,
            ),
        ]
        standings = compute_standings(games)
        chiefs = next(s for s in standings if s.team == "Chiefs")
        broncos = next(s for s in standings if s.team == "Broncos")
        raiders = next(s for s in standings if s.team == "Raiders")

        assert chiefs.games_behind == 0.0
        # Broncos: 0-1-0, Chiefs: 2-0-0 → ((2-0) + (1-0)) / 2 = 1.5
        assert broncos.games_behind == 1.5
        # Raiders: 0-1-0, Chiefs: 2-0-0 → ((2-0) + (1-0)) / 2 = 1.5
        assert raiders.games_behind == 1.5

    def test_conference_and_division_enums(self) -> None:
        """Teams should have correct conference and division assignments."""
        standings = compute_standings([])
        chiefs = next(s for s in standings if s.team == "Chiefs")
        assert chiefs.conference == Conference.AFC
        assert chiefs.division == Division.WEST

        eagles = next(s for s in standings if s.team == "Eagles")
        assert eagles.conference == Conference.NFC
        assert eagles.division == Division.EAST


class TestSimulatedOutcomes:
    """Tests for simulated outcome processing."""

    def test_simulated_win(self) -> None:
        """Simulated win should update W-L records."""
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Ravens",
                status=GameStatus.SCHEDULED,
                home_score=None, away_score=None,
                home_points=None, away_points=None,
                quarter=None, clock=None,
            ),
        ]
        simulated = [("g1", "Chiefs", False)]
        standings = compute_standings(games, simulated)

        chiefs = next(s for s in standings if s.team == "Chiefs")
        ravens = next(s for s in standings if s.team == "Ravens")

        assert chiefs.wins == 1
        assert chiefs.losses == 0
        assert ravens.wins == 0
        assert ravens.losses == 1

    def test_simulated_tie(self) -> None:
        """Simulated tie should update tie counts."""
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Ravens",
                status=GameStatus.SCHEDULED,
                home_score=None, away_score=None,
                home_points=None, away_points=None,
                quarter=None, clock=None,
            ),
        ]
        simulated = [("g1", "Chiefs", True)]
        standings = compute_standings(games, simulated)

        chiefs = next(s for s in standings if s.team == "Chiefs")
        ravens = next(s for s in standings if s.team == "Ravens")

        assert chiefs.ties == 1
        assert ravens.ties == 1

    def test_simulated_no_points(self) -> None:
        """Simulated outcomes should not contribute point data."""
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Ravens",
                status=GameStatus.SCHEDULED,
                home_score=None, away_score=None,
                home_points=None, away_points=None,
                quarter=None, clock=None,
            ),
        ]
        simulated = [("g1", "Chiefs", False)]
        standings = compute_standings(games, simulated)

        chiefs = next(s for s in standings if s.team == "Chiefs")
        assert chiefs.points_for is None
        assert chiefs.points_against is None

    def test_mixed_real_and_simulated(self) -> None:
        """Combining real and simulated results should work correctly."""
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Ravens",
                status=GameStatus.COMPLETED,
                home_score=27, away_score=20,
                home_points=27, away_points=20,
                quarter=None, clock=None,
            ),
            Game(
                game_id="g2", week=2, date=date(2024, 9, 12),
                home_team="Chiefs", away_team="Broncos",
                status=GameStatus.SCHEDULED,
                home_score=None, away_score=None,
                home_points=None, away_points=None,
                quarter=None, clock=None,
            ),
        ]
        simulated = [("g2", "Broncos", False)]  # Broncos upset Chiefs
        standings = compute_standings(games, simulated)

        chiefs = next(s for s in standings if s.team == "Chiefs")
        assert chiefs.wins == 1
        assert chiefs.losses == 1
        # Points only from real game
        assert chiefs.points_for == 27
        assert chiefs.points_against == 20

    def test_unknown_game_id_ignored(self) -> None:
        """Simulated outcomes with unknown game_id should be ignored."""
        games = [
            Game(
                game_id="g1", week=1, date=date(2024, 9, 5),
                home_team="Chiefs", away_team="Ravens",
                status=GameStatus.COMPLETED,
                home_score=27, away_score=20,
                home_points=27, away_points=20,
                quarter=None, clock=None,
            ),
        ]
        simulated = [("unknown_id", "Chiefs", False)]
        standings = compute_standings(games, simulated)

        chiefs = next(s for s in standings if s.team == "Chiefs")
        assert chiefs.wins == 1  # Only from the real game


class TestPlayoffBracketDataclass:
    """Tests for the PlayoffBracket dataclass."""

    def test_default_empty_seeds(self) -> None:
        bracket = PlayoffBracket()
        assert bracket.afc_seeds == []
        assert bracket.nfc_seeds == []

    def test_with_standings(self) -> None:
        standing = TeamStanding(
            team="Chiefs",
            conference=Conference.AFC,
            division=Division.WEST,
        )
        bracket = PlayoffBracket(afc_seeds=[standing], nfc_seeds=[])
        assert len(bracket.afc_seeds) == 1
        assert bracket.afc_seeds[0].team == "Chiefs"


def _make_standings_with_records(
    records: dict[str, tuple[int, int, int]],
) -> list[TeamStanding]:
    """Helper to create standings with specific W-L-T records for testing.

    Args:
        records: Dict mapping team name to (wins, losses, ties).
            Teams not in the dict get 0-0-0 records.

    Returns:
        List of 32 TeamStanding objects.
    """
    standings: list[TeamStanding] = []
    for conf_name, divisions in NFL_TEAMS.items():
        conf_enum = Conference(conf_name)
        for div_name, teams in divisions.items():
            div_enum = Division(div_name)
            for team in teams:
                w, l, t = records.get(team, (0, 0, 0))
                total = w + l + t
                win_pct = (w + 0.5 * t) / total if total > 0 else 0.0
                standings.append(
                    TeamStanding(
                        team=team,
                        conference=conf_enum,
                        division=div_enum,
                        wins=w,
                        losses=l,
                        ties=t,
                        win_percentage=win_pct,
                    )
                )
    return standings


class TestDeterminePlayoffBracket:
    """Tests for playoff bracket construction."""

    def test_seven_teams_per_conference(self) -> None:
        """Each conference should have exactly 7 playoff teams."""
        # Give each division one clear leader
        records = {
            # AFC division leaders
            "Chiefs": (14, 3, 0),
            "Ravens": (13, 4, 0),
            "Texans": (11, 6, 0),
            "Bills": (12, 5, 0),
            # AFC wild card contenders
            "Steelers": (10, 7, 0),
            "Dolphins": (10, 7, 0),
            "Broncos": (9, 8, 0),
            # NFC division leaders
            "Lions": (14, 3, 0),
            "Eagles": (13, 4, 0),
            "Buccaneers": (11, 6, 0),
            "49ers": (12, 5, 0),
            # NFC wild card contenders
            "Vikings": (10, 7, 0),
            "Packers": (10, 7, 0),
            "Rams": (9, 8, 0),
        }
        standings = _make_standings_with_records(records)
        bracket = determine_playoff_bracket(standings)

        assert len(bracket.afc_seeds) == 7
        assert len(bracket.nfc_seeds) == 7

    def test_division_champions_seeded_1_to_4(self) -> None:
        """Division champions should be seeded 1-4 by win percentage."""
        records = {
            # AFC: Chiefs best, Bills 2nd, Ravens 3rd, Texans 4th
            "Chiefs": (14, 3, 0),
            "Bills": (12, 5, 0),
            "Ravens": (11, 6, 0),
            "Texans": (10, 7, 0),
        }
        standings = _make_standings_with_records(records)
        bracket = determine_playoff_bracket(standings)

        afc_seeds = bracket.afc_seeds
        assert afc_seeds[0].team == "Chiefs"
        assert afc_seeds[0].seed == 1
        assert afc_seeds[1].team == "Bills"
        assert afc_seeds[1].seed == 2
        assert afc_seeds[2].team == "Ravens"
        assert afc_seeds[2].seed == 3
        assert afc_seeds[3].team == "Texans"
        assert afc_seeds[3].seed == 4

    def test_division_champions_marked(self) -> None:
        """Division champions should have is_division_champion=True."""
        records = {
            "Chiefs": (14, 3, 0),
            "Bills": (12, 5, 0),
            "Ravens": (11, 6, 0),
            "Texans": (10, 7, 0),
        }
        standings = _make_standings_with_records(records)
        bracket = determine_playoff_bracket(standings)

        for i in range(4):
            assert bracket.afc_seeds[i].is_division_champion is True

        for i in range(4, 7):
            assert bracket.afc_seeds[i].is_division_champion is False

    def test_wild_card_seeded_5_to_7(self) -> None:
        """Wild card teams should be seeded 5-7 by win percentage."""
        records = {
            # AFC division leaders
            "Chiefs": (14, 3, 0),
            "Bills": (12, 5, 0),
            "Ravens": (11, 6, 0),
            "Texans": (10, 7, 0),
            # AFC wild card contenders (non-division winners)
            "Steelers": (10, 7, 0),
            "Dolphins": (9, 8, 0),
            "Broncos": (8, 9, 0),
        }
        standings = _make_standings_with_records(records)
        bracket = determine_playoff_bracket(standings)

        # Wild cards: Steelers (10-7), Dolphins (9-8), Broncos (8-9)
        assert bracket.afc_seeds[4].team == "Steelers"
        assert bracket.afc_seeds[4].seed == 5
        assert bracket.afc_seeds[5].team == "Dolphins"
        assert bracket.afc_seeds[5].seed == 6
        assert bracket.afc_seeds[6].team == "Broncos"
        assert bracket.afc_seeds[6].seed == 7

    def test_all_playoff_teams_marked(self) -> None:
        """All 7 playoff teams should have is_playoff_team=True."""
        records = {
            "Chiefs": (14, 3, 0),
            "Bills": (12, 5, 0),
            "Ravens": (11, 6, 0),
            "Texans": (10, 7, 0),
            "Steelers": (9, 8, 0),
            "Dolphins": (8, 9, 0),
            "Broncos": (7, 10, 0),
        }
        standings = _make_standings_with_records(records)
        bracket = determine_playoff_bracket(standings)

        for team in bracket.afc_seeds:
            assert team.is_playoff_team is True

        # Non-playoff teams should remain False
        non_playoff = [s for s in standings if s.conference == Conference.AFC and not s.is_playoff_team]
        assert len(non_playoff) == 9  # 16 - 7 = 9

    def test_number_1_seed_gets_bye(self) -> None:
        """#1 seed should not appear in Wild Card matchups (gets bye)."""
        records = {
            "Chiefs": (14, 3, 0),
            "Bills": (12, 5, 0),
            "Ravens": (11, 6, 0),
            "Texans": (10, 7, 0),
            "Steelers": (9, 8, 0),
            "Dolphins": (8, 9, 0),
            "Broncos": (7, 10, 0),
        }
        standings = _make_standings_with_records(records)
        bracket = determine_playoff_bracket(standings)
        matchups = get_wild_card_matchups(bracket)

        # #1 seed (Chiefs) should not be in any matchup
        for matchup in matchups["AFC"]:
            assert matchup.home_team.team != "Chiefs"
            assert matchup.away_team.team != "Chiefs"

    def test_wild_card_pairings_2v7_3v6_4v5(self) -> None:
        """Wild Card pairings should be 2v7, 3v6, 4v5."""
        records = {
            "Chiefs": (14, 3, 0),
            "Bills": (12, 5, 0),
            "Ravens": (11, 6, 0),
            "Texans": (10, 7, 0),
            "Steelers": (9, 8, 0),
            "Dolphins": (8, 9, 0),
            "Broncos": (7, 10, 0),
        }
        standings = _make_standings_with_records(records)
        bracket = determine_playoff_bracket(standings)
        matchups = get_wild_card_matchups(bracket)

        afc_matchups = matchups["AFC"]
        assert len(afc_matchups) == 3

        # 2v7: Bills vs Broncos
        assert afc_matchups[0].home_seed == 2
        assert afc_matchups[0].away_seed == 7
        assert afc_matchups[0].home_team.team == "Bills"
        assert afc_matchups[0].away_team.team == "Broncos"

        # 3v6: Ravens vs Dolphins
        assert afc_matchups[1].home_seed == 3
        assert afc_matchups[1].away_seed == 6
        assert afc_matchups[1].home_team.team == "Ravens"
        assert afc_matchups[1].away_team.team == "Dolphins"

        # 4v5: Texans vs Steelers
        assert afc_matchups[2].home_seed == 4
        assert afc_matchups[2].away_seed == 5
        assert afc_matchups[2].home_team.team == "Texans"
        assert afc_matchups[2].away_team.team == "Steelers"

    def test_higher_seed_hosts(self) -> None:
        """Higher seed should always be the home team in matchups."""
        records = {
            "Chiefs": (14, 3, 0),
            "Bills": (12, 5, 0),
            "Ravens": (11, 6, 0),
            "Texans": (10, 7, 0),
            "Steelers": (9, 8, 0),
            "Dolphins": (8, 9, 0),
            "Broncos": (7, 10, 0),
        }
        standings = _make_standings_with_records(records)
        bracket = determine_playoff_bracket(standings)
        matchups = get_wild_card_matchups(bracket)

        for matchup in matchups["AFC"]:
            assert matchup.home_seed < matchup.away_seed

    def test_tiebreaker_alphabetical_fallback(self) -> None:
        """When teams have equal win_percentage, alphabetical order breaks tie."""
        # Two division champions with same record
        records = {
            "Chiefs": (12, 5, 0),  # AFC West
            "Bills": (12, 5, 0),   # AFC East — "Bills" < "Chiefs" alphabetically
            "Ravens": (10, 7, 0),  # AFC North
            "Texans": (9, 8, 0),   # AFC South
        }
        standings = _make_standings_with_records(records)
        bracket = determine_playoff_bracket(standings)

        # Bills comes before Chiefs alphabetically
        assert bracket.afc_seeds[0].team == "Bills"
        assert bracket.afc_seeds[0].seed == 1
        assert bracket.afc_seeds[1].team == "Chiefs"
        assert bracket.afc_seeds[1].seed == 2

    def test_both_conferences_populated(self) -> None:
        """Both AFC and NFC brackets should be populated."""
        records = {
            # AFC
            "Chiefs": (14, 3, 0),
            "Bills": (12, 5, 0),
            "Ravens": (11, 6, 0),
            "Texans": (10, 7, 0),
            "Steelers": (9, 8, 0),
            "Dolphins": (8, 9, 0),
            "Broncos": (7, 10, 0),
            # NFC
            "Lions": (14, 3, 0),
            "Eagles": (12, 5, 0),
            "Buccaneers": (11, 6, 0),
            "49ers": (10, 7, 0),
            "Vikings": (9, 8, 0),
            "Packers": (8, 9, 0),
            "Rams": (7, 10, 0),
        }
        standings = _make_standings_with_records(records)
        bracket = determine_playoff_bracket(standings)

        assert len(bracket.afc_seeds) == 7
        assert len(bracket.nfc_seeds) == 7

        # Verify NFC bracket
        assert bracket.nfc_seeds[0].team == "Lions"
        assert bracket.nfc_seeds[0].seed == 1

    def test_standings_updated_in_place(self) -> None:
        """determine_playoff_bracket should update TeamStanding objects in place."""
        records = {
            "Chiefs": (14, 3, 0),
            "Bills": (12, 5, 0),
            "Ravens": (11, 6, 0),
            "Texans": (10, 7, 0),
            "Steelers": (9, 8, 0),
            "Dolphins": (8, 9, 0),
            "Broncos": (7, 10, 0),
        }
        standings = _make_standings_with_records(records)
        determine_playoff_bracket(standings)

        # Check that the original standings objects were modified
        chiefs = next(s for s in standings if s.team == "Chiefs")
        assert chiefs.seed == 1
        assert chiefs.is_division_champion is True
        assert chiefs.is_playoff_team is True

        # Non-playoff team should remain unchanged
        raiders = next(s for s in standings if s.team == "Raiders")
        assert raiders.seed is None
        assert raiders.is_division_champion is False
        assert raiders.is_playoff_team is False

    def test_all_zero_records(self) -> None:
        """With all 0-0-0 records, bracket should still be constructed (alphabetical order)."""
        standings = _make_standings_with_records({})
        bracket = determine_playoff_bracket(standings)

        assert len(bracket.afc_seeds) == 7
        assert len(bracket.nfc_seeds) == 7

        # All teams have 0.0 win_pct, so alphabetical order determines seeding
        # AFC division champions (alphabetical first in each division):
        # East: Bills, North: Bengals, South: Colts, West: Broncos
        # Sorted alphabetically: Bengals, Bills, Broncos, Colts
        afc_champs = [bracket.afc_seeds[i].team for i in range(4)]
        assert "Bills" in afc_champs
        assert "Bengals" in afc_champs
        assert "Colts" in afc_champs
        assert "Broncos" in afc_champs


class TestSortTeamsByRecord:
    """Tests for the _sort_teams_by_record helper."""

    def test_sorts_by_win_percentage_descending(self) -> None:
        teams = [
            TeamStanding(team="A", conference=Conference.AFC, division=Division.EAST, win_percentage=0.5),
            TeamStanding(team="B", conference=Conference.AFC, division=Division.EAST, win_percentage=0.8),
            TeamStanding(team="C", conference=Conference.AFC, division=Division.EAST, win_percentage=0.3),
        ]
        result = _sort_teams_by_record(teams)
        assert [t.team for t in result] == ["B", "A", "C"]

    def test_alphabetical_tiebreaker(self) -> None:
        teams = [
            TeamStanding(team="Zebras", conference=Conference.AFC, division=Division.EAST, win_percentage=0.5),
            TeamStanding(team="Alphas", conference=Conference.AFC, division=Division.EAST, win_percentage=0.5),
        ]
        result = _sort_teams_by_record(teams)
        assert [t.team for t in result] == ["Alphas", "Zebras"]


class TestWildCardMatchup:
    """Tests for the WildCardMatchup dataclass."""

    def test_matchup_creation(self) -> None:
        home = TeamStanding(team="Bills", conference=Conference.AFC, division=Division.EAST, seed=2)
        away = TeamStanding(team="Broncos", conference=Conference.AFC, division=Division.WEST, seed=7)
        matchup = WildCardMatchup(home_seed=2, away_seed=7, home_team=home, away_team=away)

        assert matchup.home_seed == 2
        assert matchup.away_seed == 7
        assert matchup.home_team.team == "Bills"
        assert matchup.away_team.team == "Broncos"
