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
