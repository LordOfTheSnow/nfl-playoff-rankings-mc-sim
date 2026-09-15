"""Tests for the HTML export feature (src/export.py + POST /api/export/*).

Covers:
- src/export.validate_simulation_payload: defensive validation of the
  client-forwarded simulation result (Hypothesis-driven, since the shapes
  are easy to generate and the function must never raise).
- Team-slug uniqueness across all 32 teams (guards the bundle's per-team
  filenames against future collisions).
- POST /api/export/page and POST /api/export/bundle end to end, using the
  same FakeHandler-over-a-real-server pattern as test_simulate_job.py /
  test_schedule_grid.py, since these endpoints reuse the real standings/
  statistics/schedule-grid/team-detail computation via _capture_json_response
  rather than duplicating it.
"""

from __future__ import annotations

import json
import zipfile
from datetime import date
from io import BytesIO

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src import export
from src.data_client import Game, GameStatus
from src.nfl_teams import ALL_TEAMS
from src.server import NFLRequestHandler, NFLSimulatorServer


class FakeHandler(NFLRequestHandler):
    """Captures responses without real sockets (mirrors test_simulate_job.py)."""

    def __init__(self, path: str, server: NFLSimulatorServer, body: dict | None = None):
        self.path = path
        self.server = server
        # None mirrors _parse_json_body()'s real "invalid JSON" return value;
        # a dict (possibly {}) mirrors a valid (possibly empty) body.
        self._body = body
        self.headers = {"Content-Length": "0"}
        self.rfile = BytesIO(b"")
        self.wfile = BytesIO()
        self._sent_code: int | None = None
        self._sent_headers: list[tuple[str, str]] = []

    def _parse_json_body(self) -> dict | None:
        return self._body

    def send_response(self, code, message=None):
        self._sent_code = code

    def send_header(self, keyword, value):
        self._sent_headers.append((keyword, value))

    def end_headers(self):
        pass

    def log_message(self, format, *args):
        pass

    def header(self, name: str) -> str | None:
        return next((v for k, v in self._sent_headers if k == name), None)


@pytest.fixture
def server_with_games() -> NFLSimulatorServer:
    server = NFLSimulatorServer(port=0, season_year=2026, db_path=":memory:")
    games = [
        Game(game_id="g1", week=1, date=date(2026, 9, 7), home_team="Bills", away_team="Jets",
             status=GameStatus.COMPLETED, home_score=24, away_score=10, home_points=24, away_points=10),
        Game(game_id="g2", week=2, date=date(2026, 9, 14), home_team="Bills", away_team="Dolphins",
             status=GameStatus.COMPLETED, home_score=20, away_score=20, home_points=20, away_points=20),
        Game(game_id="g3", week=3, date=date(2026, 9, 21), home_team="Chiefs", away_team="Broncos",
             status=GameStatus.COMPLETED, home_score=31, away_score=17, home_points=31, away_points=17),
        Game(game_id="g4", week=4, date=date(2026, 9, 28), home_team="Bills", away_team="Patriots",
             status=GameStatus.SCHEDULED),
    ]
    server.cache.store_games(games, 2026)
    yield server
    server.cache.close()


SAMPLE_SIM_RESULT = {
    "team_results": [
        {
            "team": "Bills", "conference": "AFC", "division": "East", "record": "1-0-1",
            "playoff_probability": 55.5, "strength_rating": 1.05,
            "seed_probabilities": {"1": 5, "2": 10, "3": 15, "4": 10, "5": 10, "6": 5, "7": 0.5},
        },
    ],
    "top_scenarios": [
        {"afc_seeds": ["Bills"], "nfc_seeds": [], "probability": 12.3},
    ],
    "iterations_run": 5000,
    "cutoff_week_used": 3,
    "low_confidence": False,
    "convergence_achieved": True,
    "team_strengths": {"Bills": 1.05},
    "fixed_games": 3,
    "simulated_games": 269,
}


class TestValidateSimulationPayload:
    def test_accepts_well_formed_payload(self) -> None:
        assert export.validate_simulation_payload(SAMPLE_SIM_RESULT) == SAMPLE_SIM_RESULT

    def test_rejects_none(self) -> None:
        assert export.validate_simulation_payload(None) is None

    @given(st.one_of(st.text(), st.integers(), st.lists(st.integers()), st.none()))
    @settings(max_examples=25)
    def test_rejects_non_dict_without_raising(self, value: object) -> None:
        assert export.validate_simulation_payload(value) is None

    @given(st.dictionaries(st.text(min_size=1, max_size=8), st.text(), max_size=5))
    @settings(max_examples=50)
    def test_rejects_arbitrary_dicts_missing_required_keys_without_raising(
        self, value: dict
    ) -> None:
        # An arbitrary dict essentially never happens to contain valid
        # team_results/top_scenarios lists -- this asserts the function
        # degrades to "no simulation" instead of raising on garbage input.
        assert export.validate_simulation_payload(value) is None

    def test_rejects_unknown_team_name(self) -> None:
        bad = json.loads(json.dumps(SAMPLE_SIM_RESULT))
        bad["team_results"][0]["team"] = "Not A Real Team"
        assert export.validate_simulation_payload(bad) is None

    def test_rejects_seed_probabilities_not_a_dict(self) -> None:
        bad = json.loads(json.dumps(SAMPLE_SIM_RESULT))
        bad["team_results"][0]["seed_probabilities"] = [1, 2, 3]
        assert export.validate_simulation_payload(bad) is None


class TestTeamSlugs:
    def test_all_32_team_slugs_are_unique(self) -> None:
        slugs = [export._slug(team) for team in ALL_TEAMS]
        assert len(slugs) == len(set(slugs)) == 32

    def test_bundle_team_link_matches_slug(self) -> None:
        for team in ALL_TEAMS:
            assert export.bundle_team_link(team) == f"team-{export._slug(team)}.html"


class TestExportPageEndpoint:
    def test_returns_html_with_all_sections_when_simulation_supplied(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/export/page", server_with_games, body={"simulation_result": SAMPLE_SIM_RESULT})
        handler._handle_export_page()

        assert handler._sent_code == 200
        assert handler.header("Content-Type") == "text/html; charset=utf-8"
        html = handler.wfile.getvalue().decode("utf-8")
        assert "<!doctype html>" in html.lower()
        assert "Standings" in html
        assert "Statistics" in html
        assert "Schedule Grid" in html
        assert "Simulation" in html
        assert "Bills" in html

    def test_simulation_section_includes_season_data_card_and_games_total(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        """The Simulation section should carry the same "Season data" card
        and "N games x M iterations = X game simulations" line shown on the
        live Simulations page header (buildSeasonDataCell / sim-total-sim)."""
        handler = FakeHandler(
            "/api/export/page",
            server_with_games,
            body={"simulation_result": SAMPLE_SIM_RESULT, "cutoff_week": 3},
        )
        handler._handle_export_page()

        assert handler._sent_code == 200
        html = handler.wfile.getvalue().decode("utf-8")
        assert "Season data" in html
        assert "Week 3 cutoff" in html
        assert "Weeks loaded" in html
        assert "Games completed" in html
        expected_total = SAMPLE_SIM_RESULT["simulated_games"] * SAMPLE_SIM_RESULT["iterations_run"]
        assert f"{expected_total:,} game simulations" in html

    def test_omits_simulation_section_when_not_supplied(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/export/page", server_with_games, body={})
        handler._handle_export_page()

        assert handler._sent_code == 200
        html = handler.wfile.getvalue().decode("utf-8")
        assert "Simulation" not in html

    def test_single_page_has_no_team_links(self, server_with_games: NFLSimulatorServer) -> None:
        """Explicit user decision: the combined page keeps team names as plain
        text (no per-team links/sections) to keep the page manageable."""
        handler = FakeHandler("/api/export/page", server_with_games, body={})
        handler._handle_export_page()
        html = handler.wfile.getvalue().decode("utf-8")
        assert "team-bills.html" not in html
        assert '<a class="mdn-team-link"' not in html

    def test_malformed_json_body_returns_400(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/export/page", server_with_games, body=None)
        handler._handle_export_page()
        assert handler._sent_code == 400

    def test_no_cached_data_returns_409(self) -> None:
        empty_server = NFLSimulatorServer(port=0, season_year=2099, db_path=":memory:")
        try:
            handler = FakeHandler("/api/export/page", empty_server, body={})
            handler._handle_export_page()
            assert handler._sent_code == 409
        finally:
            empty_server.cache.close()

    def test_tampered_simulation_payload_is_dropped_not_500(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        bad_payload = {"team_results": "not-a-list", "top_scenarios": []}
        handler = FakeHandler("/api/export/page", server_with_games, body={"simulation_result": bad_payload})
        handler._handle_export_page()
        assert handler._sent_code == 200
        html = handler.wfile.getvalue().decode("utf-8")
        assert "Simulation" not in html


class TestExportBundleEndpoint:
    def test_bundle_contains_expected_files(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/export/bundle", server_with_games, body={"simulation_result": SAMPLE_SIM_RESULT})
        handler._handle_export_bundle()

        assert handler._sent_code == 200
        assert handler.header("Content-Type") == "application/zip"
        assert "attachment" in (handler.header("Content-Disposition") or "")

        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))
        names = set(zf.namelist())
        assert "index.html" in names
        assert "standings.html" in names
        assert "statistics.html" in names
        assert "schedule-grid.html" in names
        assert "simulations.html" in names
        assert "styles.css" in names
        for team in ALL_TEAMS:
            assert f"team-{export._slug(team)}.html" in names
        for logo_id in export.ALL_LOGO_IDS:
            assert f"img/logos/{logo_id}.png" in names
        assert len(names) == 6 + 32 + len(export.ALL_LOGO_IDS)

    def test_omits_simulations_page_when_no_simulation_supplied(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/export/bundle", server_with_games, body={})
        handler._handle_export_bundle()
        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))
        assert "simulations.html" not in zf.namelist()

    def test_team_names_link_everywhere_in_the_bundle(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/export/bundle", server_with_games, body={"simulation_result": SAMPLE_SIM_RESULT})
        handler._handle_export_bundle()
        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))

        standings_html = zf.read("standings.html").decode("utf-8")
        assert "team-bills.html" in standings_html

        schedule_html = zf.read("schedule-grid.html").decode("utf-8")
        assert "team-bills.html" in schedule_html

        sim_html = zf.read("simulations.html").decode("utf-8")
        assert "team-bills.html" in sim_html

        index_html = zf.read("index.html").decode("utf-8")
        assert "team-bills.html" in index_html

    def test_malformed_json_body_returns_400(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/export/bundle", server_with_games, body=None)
        handler._handle_export_bundle()
        assert handler._sent_code == 400

    def test_no_cached_data_returns_409(self) -> None:
        empty_server = NFLSimulatorServer(port=0, season_year=2099, db_path=":memory:")
        try:
            handler = FakeHandler("/api/export/bundle", empty_server, body={})
            handler._handle_export_bundle()
            assert handler._sent_code == 409
        finally:
            empty_server.cache.close()
