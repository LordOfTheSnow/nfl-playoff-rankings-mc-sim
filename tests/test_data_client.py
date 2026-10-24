"""Unit tests for ESPN team name resolution in data_client.py."""

from src.data_client import _resolve_team_name


class TestResolveTeamName:
    """Tests for _resolve_team_name()."""

    def test_current_display_name_resolves_via_mapping(self):
        """A team's current ESPN display name resolves via the explicit mapping."""
        assert _resolve_team_name("Kansas City Chiefs") == "Chiefs"

    def test_unmapped_two_word_name_resolves_via_last_word_fallback(self):
        """A display name not in the mapping still resolves if its last word is a known team."""
        assert _resolve_team_name("Some New Chiefs") == "Chiefs"

    def test_washington_historical_names_all_resolve_to_commanders(self):
        """Washington's three ESPN eras (Redskins / Football Team / Commanders) all
        resolve to the current canonical name. Regression test: before the current
        franchise's full name was added, "Washington Football Team" fell through to
        the last-word fallback ("Team", not a real team), and bare "Washington" (what
        ESPN actually returned for the 2020-2021 seasons) isn't a known team either —
        both silently returned the raw, unresolved string. Since compute_standings()
        drops any game where either side isn't a recognized team name, this made every
        Washington game vanish from both participants' 2020/2021 records.
        """
        for espn_name in (
            "Washington Redskins",
            "Washington Football Team",
            "Washington",
            "Washington Commanders",
        ):
            assert _resolve_team_name(espn_name) == "Commanders", espn_name

    def test_relocated_franchises_resolve_to_current_short_name(self):
        """Historical city names for since-relocated franchises resolve correctly."""
        assert _resolve_team_name("Oakland Raiders") == "Raiders"
        assert _resolve_team_name("San Diego Chargers") == "Chargers"
        assert _resolve_team_name("St. Louis Rams") == "Rams"

    def test_unresolvable_name_returns_raw_string(self):
        """A name that can't be resolved via mapping or last-word fallback is
        returned as-is (the caller logs a warning) rather than raising."""
        assert _resolve_team_name("Totally Unknown Team") == "Totally Unknown Team"


# ---------------------------------------------------------------------------
# Kickoff parsing
# ---------------------------------------------------------------------------

from datetime import UTC, date, datetime  # noqa: E402

from hypothesis import given, settings  # noqa: E402

from src.data_client import parse_espn_event  # noqa: E402
from tests.strategies.espn_json import espn_event  # noqa: E402


class TestParseKickoff:
    """parse_espn_event keeps the full UTC kickoff and ESPN's timeValid."""

    @given(event=espn_event())
    @settings(max_examples=100)
    def test_kickoff_matches_espn_date(self, event: dict) -> None:
        game = parse_espn_event(event)
        expected = datetime.fromisoformat(event["date"])
        assert game.kickoff == expected
        assert game.kickoff.tzinfo is not None
        assert game.kickoff.utcoffset().total_seconds() == 0
        # `date` stays the UTC calendar date of the kickoff
        assert game.date == game.kickoff.date()
        assert game.kickoff_time_valid == event["competitions"][0]["timeValid"]

    @given(event=espn_event())
    @settings(max_examples=20)
    def test_missing_time_valid_defaults_to_true(self, event: dict) -> None:
        del event["competitions"][0]["timeValid"]
        assert parse_espn_event(event).kickoff_time_valid is True

    @given(event=espn_event())
    @settings(max_examples=20)
    def test_thursday_night_kickoff_keeps_time(self, event: dict) -> None:
        """2026 week 7 TNF: 8:15pm ET Thursday is 00:15Z on Friday."""
        event["date"] = "2026-10-23T00:15Z"
        game = parse_espn_event(event)
        assert game.kickoff == datetime(2026, 10, 23, 0, 15, tzinfo=UTC)
        assert game.date == date(2026, 10, 23)
