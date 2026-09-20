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
import re
from datetime import date, datetime, timedelta, timezone
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


class TestGridCell:
    """_grid_cell renders each week's slot the same way the frontend's
    schedule-grid.js does: opponent on one line, a sub-label (score or
    status) on the line below — no W/L/T letter, since the live app's
    grid cells don't show one either.
    """

    def test_bye_week(self) -> None:
        assert export._grid_cell(None) == '<span class="mdn-bye">BYE</span>'

    def test_completed_home_game_has_no_win_loss_letter(self) -> None:
        slot = {
            "opponent": "SEA", "home": True, "status": "completed",
            "team_score": 26, "opponent_score": 14,
        }
        html = export._grid_cell(slot)
        assert "<div>vs SEA</div>" in html
        assert '<div class="mdn-hint" style="font-size:10px">26-14</div>' in html
        assert "W" not in html and "L" not in html

    def test_completed_away_game_uses_at_prefix(self) -> None:
        slot = {
            "opponent": "LAC", "home": False, "status": "completed",
            "team_score": 14, "opponent_score": 26,
        }
        html = export._grid_cell(slot)
        assert "<div>@ LAC</div>" in html
        assert '<div class="mdn-hint" style="font-size:10px">14-26</div>' in html

    def test_in_progress_game_shows_r_suffix(self) -> None:
        slot = {
            "opponent": "SEA", "home": True, "status": "in-progress",
            "team_score": 10, "opponent_score": 7,
        }
        html = export._grid_cell(slot)
        assert '<div class="mdn-hint" style="font-size:10px">10-7 (r)</div>' in html

    def test_postponed_game(self) -> None:
        slot = {
            "opponent": "SEA", "home": True, "status": "postponed",
            "team_score": None, "opponent_score": None,
        }
        html = export._grid_cell(slot)
        assert "<div>vs SEA</div>" in html
        assert "Postponed" in html

    def test_cancelled_game(self) -> None:
        slot = {
            "opponent": "SEA", "home": True, "status": "cancelled",
            "team_score": None, "opponent_score": None,
        }
        html = export._grid_cell(slot)
        assert "<div>vs SEA</div>" in html
        assert "Canceled" in html

    def test_scheduled_game_with_no_scores_shows_opponent_only(self) -> None:
        slot = {
            "opponent": "SEA", "home": True, "status": "scheduled",
            "team_score": None, "opponent_score": None,
        }
        assert export._grid_cell(slot) == "vs SEA"


class TestSeedTint:
    """_seed_tint mirrors simulation.js's _seedTint bucket-for-bucket, so the
    exported seeding matrix's heatmap matches the live one exactly.
    """

    def test_zero_is_transparent_and_not_hi(self) -> None:
        assert export._seed_tint(0) == ("transparent", False)

    def test_below_15_is_lightest_non_hi_bucket(self) -> None:
        tint, hi = export._seed_tint(14.9)
        assert tint == "oklch(91% 0.045 55)"
        assert hi is False

    def test_60_is_first_hi_bucket(self) -> None:
        _, hi = export._seed_tint(60)
        assert hi is True

    def test_100_is_darkest_bucket(self) -> None:
        tint, hi = export._seed_tint(100)
        assert tint == "oklch(34% 0.10 30)"
        assert hi is True


class TestDataConfidenceLine:
    """The "Data-driven ratings" indicator under the Results line."""

    def _result(self, **overrides):
        return {**SAMPLE_SIM_RESULT, "data_driven_pct": 11.1, "data_confidence": "Very low", **overrides}

    def test_shows_pct_label_and_games_played(self) -> None:
        line = export._data_confidence_line(self._result(fixed_games=1, simulated_games=271))
        assert "Data-driven ratings: 11% — Very low" in line
        assert "1 of 272 games played (0.4%)" in line

    def test_rounds_half_up(self) -> None:
        assert "Data-driven ratings: 13%" in export._data_confidence_line(self._result(data_driven_pct=12.5))

    def test_games_played_pct_rounds_exact_ties_half_up_like_the_live_app(self) -> None:
        # 17/272 = 6.25% exactly: JS toFixed(1) gives "6.3", Python's :.1f "6.2".
        line = export._data_confidence_line(self._result(fixed_games=17, simulated_games=255))
        assert "17 of 272 games played (6.3%)" in line

    def test_omitted_for_results_without_the_field(self) -> None:
        assert export._data_confidence_line(SAMPLE_SIM_RESULT) == ""

    @pytest.mark.parametrize("bad", ["11", None, True, [1]])
    def test_malformed_value_is_omitted(self, bad) -> None:
        assert export._data_confidence_line(self._result(data_driven_pct=bad)) == ""

    def test_label_is_escaped(self) -> None:
        line = export._data_confidence_line(self._result(data_confidence="<script>x</script>"))
        assert "<script>" not in line

    def test_rendered_first_in_simulation_content(self) -> None:
        html = export.render_simulation_content(self._result(), lambda _n: None, export.make_inline_logo_renderer())
        assert html.startswith('<p class="mdn-hint" style="margin:0 0 16px"><strong>Data-driven ratings')


class TestExportHeader:
    """Every page opens with the live app's NFL logo brand bar and the
    independence disclaimer, wired in once via _page_shell."""

    def test_header_has_logo_brand_and_disclaimer(self) -> None:
        html = export._page_shell("T", "<p>x</p>", logo=export.bundle_logo)
        assert '<nav class="mdn-nav">' in html
        assert 'src="img/logos/nfl.png"' in html
        assert "NFL PLAYOFF RANKINGS SIM" in html
        assert '<div class="mdn-disclaimer">' in html
        assert "not affiliated with the NFL" in html
        assert html.index("mdn-nav") < html.index("<main")

    def test_brand_links_only_when_href_given(self) -> None:
        plain = export._page_shell("T", "", logo=export.bundle_logo)
        linked = export._page_shell("T", "", logo=export.bundle_logo, brand_href="index.html")
        assert '<a class="mdn-brand" href="index.html">' in linked
        assert '<div class="mdn-brand">' in plain

    def test_inline_renderer_uses_nfl_logo_class(self) -> None:
        html = export._page_shell("T", "", logo=export.make_inline_logo_renderer())
        assert 'class="logo-nfl"' in html

    def test_nfl_logo_is_exported(self) -> None:
        assert "nfl" in export.ALL_LOGO_IDS


class TestExportFooter:
    """Every generated page (single-page export, and every page in the
    bundle) gets a "Created by <project> v<version> on <date time tz>. — View on GitHub"
    footer, divided from the page content by a horizontal rule -- wired in
    once via _page_shell rather than at each call site, so it can't be
    missed on any individual page. The line also carries the export date.
    """

    footer = export._export_footer(datetime(2026, 9, 20, 17, 5, tzinfo=timezone(timedelta(hours=2))))
    # Every page's footer carries a stamp shaped like "2026-09-20 17:05 UTC+02:00".
    footer_pattern = re.compile(r"on \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC[+-]\d{2}:\d{2}\. — ")

    def test_footer_shows_date_time_and_utc_offset(self) -> None:
        assert " on 2026-09-20 17:05 UTC+02:00. — " in self.footer

    def test_footer_formats_negative_and_half_hour_offsets(self) -> None:
        tz = timezone(timedelta(hours=-3, minutes=-30))
        footer = export._export_footer(datetime(2026, 1, 2, 3, 4, tzinfo=tz))
        assert " on 2026-01-02 03:04 UTC-03:30. — " in footer

    def test_footer_defaults_to_now_with_local_offset(self) -> None:
        assert self.footer_pattern.search(export._export_footer())

    def test_footer_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError):
            export._export_footer(datetime(2026, 9, 20, 17, 5))

    def test_bundle_pages_share_one_timestamp(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/export/bundle", server_with_games, body={})
        handler._handle_export_bundle()
        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))
        stamps = {
            self.footer_pattern.search(zf.read(n).decode("utf-8")).group(0)
            for n in zf.namelist() if n.endswith(".html")
        }
        assert len(stamps) == 1

    def test_footer_has_divider_credit_and_github_link(self) -> None:
        assert '<div style="border-top:2px solid var(--mdn-divider);margin-top:32px"></div>' in self.footer
        assert f"Created by {export._PROJECT_NAME} v{export._PROJECT_VERSION} on 2026-09-20 17:05 UTC+02:00." in self.footer
        assert f'href="{export._GITHUB_REPO_URL}"' in self.footer
        assert "View on GitHub" in self.footer
        assert "<svg" in self.footer

    def test_footer_github_link_opens_in_new_tab_safely(self) -> None:
        assert 'target="_blank"' in self.footer
        # target="_blank" without rel="noopener" lets the opened page access
        # window.opener and repoint it (a reverse tabnabbing risk).
        assert 'rel="noopener noreferrer"' in self.footer

    def test_footer_dash_is_separated_from_the_link(self) -> None:
        """The em dash sits as plain text before the anchor, with a space on
        each side, rather than being glued to (or part of) the link itself."""
        assert "— <a" in self.footer
        assert "—<a" not in self.footer

    def test_footer_present_on_single_page_export(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/export/page", server_with_games, body={})
        handler._handle_export_page()
        html = handler.wfile.getvalue().decode("utf-8")
        assert self.footer_pattern.search(html)
        # Divider + footer come after the page content, right before the
        # closing wrapper tags, not injected mid-page.
        assert html.rstrip().endswith("</a></p></div></main></body></html>")

    def test_footer_present_on_every_bundle_page(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/export/bundle", server_with_games, body={"simulation_result": SAMPLE_SIM_RESULT})
        handler._handle_export_bundle()
        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))
        root = export._BUNDLE_ROOT

        for filename in [
            "index.html", "standings.html", "statistics.html",
            "schedule-grid.html", "simulations.html", "team-bills.html",
        ]:
            html = zf.read(f"{root}/{filename}").decode("utf-8")
            assert self.footer_pattern.search(html), f"{filename} missing export footer"


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

    def test_seeding_matrix_cells_are_tinted_like_the_live_app(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        """Regression test: the exported seeding matrix must carry the same
        per-cell background tint + mdn-seed-hi class as simulation.js's
        _seedTint, not plain untinted percentages."""
        handler = FakeHandler("/api/export/page", server_with_games, body={"simulation_result": SAMPLE_SIM_RESULT})
        handler._handle_export_page()

        html = handler.wfile.getvalue().decode("utf-8")
        # Bills' seed 3 probability is 15 -> oklch(82% 0.09 48), not hi
        assert 'style="background:oklch(82% 0.09 48);font-weight:700">15.0%' in html
        # Bills' seed 7 probability is 0.5 -> lightest bucket, not hi
        assert 'style="background:oklch(91% 0.045 55);font-weight:700">0.5%' in html

    def test_season_data_card_is_at_top_of_page_with_game_simulations_tile(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        """The Season Data card sits at the very top of the page, before the
        Standings section -- not down in the Simulation section -- so season
        context is visible regardless of which sections the export includes.
        When a simulation is exported, its games x iterations = total figure
        is folded into that same card as a fifth "Game simulations" tile
        instead of being left as an orphaned standalone line."""
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
        assert "Game simulations" in html
        games_to_sim = SAMPLE_SIM_RESULT["simulated_games"]
        iterations = SAMPLE_SIM_RESULT["iterations_run"]
        expected_total = games_to_sim * iterations
        assert f"{games_to_sim:,} × {iterations:,} = {expected_total:,}" in html

        season_data_idx = html.index("Season data")
        sim_tile_idx = html.index("Game simulations")
        standings_idx = html.index(">Standings<")
        assert season_data_idx < sim_tile_idx < standings_idx

    def test_season_data_card_present_without_game_simulations_tile_when_no_simulation(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        """The Season Data card is general season/cutoff context, not tied to
        whether a simulation was run, so it still appears at the top of the
        page with no simulation supplied -- just without the "Game
        simulations" tile, which has nothing to report."""
        handler = FakeHandler("/api/export/page", server_with_games, body={})
        handler._handle_export_page()

        assert handler._sent_code == 200
        html = handler.wfile.getvalue().decode("utf-8")
        assert "Season data" in html
        assert "Game simulations" not in html

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

    def test_has_no_all_caps_export_heading(self, server_with_games: NFLSimulatorServer) -> None:
        """The page header (nav bar) already carries the brand, so the
        single-page export has no separate "... Export — <year>" <h1>; the
        season is shown by the Season data card instead."""
        handler = FakeHandler("/api/export/page", server_with_games, body={})
        handler._handle_export_page()
        html = handler.wfile.getvalue().decode("utf-8")
        assert "SIM Export —" not in html
        assert "<title>NFL Playoff Rankings Monte Carlo Simulator — 2026 Export</title>" in html
        assert "<h1" not in html
        assert "NFL PLAYOFF RANKINGS SIM" in html  # nav bar brand
        assert "Season data" in html

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


def test_export_filename_is_shared_slug_season_and_extension() -> None:
    assert export.export_filename(2026, "zip") == "nfl-playoff-rankings-mc-sim-export-2026.zip"
    assert export.export_filename(2026, "html") == "nfl-playoff-rankings-mc-sim-export-2026.html"


class TestExportBundleEndpoint:
    def test_bundle_contains_expected_files(self, server_with_games: NFLSimulatorServer) -> None:
        handler = FakeHandler("/api/export/bundle", server_with_games, body={"simulation_result": SAMPLE_SIM_RESULT})
        handler._handle_export_bundle()

        assert handler._sent_code == 200
        assert handler.header("Content-Type") == "application/zip"
        assert "attachment" in (handler.header("Content-Disposition") or "")
        assert f'filename="{export.export_filename(server_with_games.season_year, "zip")}"' in (handler.header("Content-Disposition") or "")

        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))
        names = set(zf.namelist())
        root = export._BUNDLE_ROOT
        # Every file lives under a single top-level folder, not loose at
        # the ZIP root, so extracting the archive doesn't scatter 38+ files.
        assert all(name.startswith(f"{root}/") for name in names)
        assert f"{root}/index.html" in names
        assert f"{root}/standings.html" in names
        assert f"{root}/statistics.html" in names
        assert f"{root}/schedule-grid.html" in names
        assert f"{root}/simulations.html" in names
        assert f"{root}/styles.css" in names
        for team in ALL_TEAMS:
            assert f"{root}/team-{export._slug(team)}.html" in names
        for logo_id in export.ALL_LOGO_IDS:
            assert f"{root}/img/logos/{logo_id}.png" in names
        assert len(names) == 6 + 32 + len(export.ALL_LOGO_IDS)

    def test_omits_simulations_page_when_no_simulation_supplied(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/export/bundle", server_with_games, body={})
        handler._handle_export_bundle()
        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))
        assert f"{export._BUNDLE_ROOT}/simulations.html" not in zf.namelist()

    def test_team_names_link_everywhere_in_the_bundle(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        handler = FakeHandler("/api/export/bundle", server_with_games, body={"simulation_result": SAMPLE_SIM_RESULT})
        handler._handle_export_bundle()
        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))
        root = export._BUNDLE_ROOT

        standings_html = zf.read(f"{root}/standings.html").decode("utf-8")
        assert "team-bills.html" in standings_html

        schedule_html = zf.read(f"{root}/schedule-grid.html").decode("utf-8")
        assert "team-bills.html" in schedule_html

        sim_html = zf.read(f"{root}/simulations.html").decode("utf-8")
        assert "team-bills.html" in sim_html

        index_html = zf.read(f"{root}/index.html").decode("utf-8")
        assert "team-bills.html" in index_html

    def test_back_to_index_link_on_every_page_except_index(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        """Every page except index.html itself gets a back-link to it --
        the 4 section pages (previously missing one) and every team page
        (which already had one)."""
        handler = FakeHandler("/api/export/bundle", server_with_games, body={"simulation_result": SAMPLE_SIM_RESULT})
        handler._handle_export_bundle()
        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))
        root = export._BUNDLE_ROOT

        index_html = zf.read(f"{root}/index.html").decode("utf-8")
        assert 'href="index.html" class="mdn-back-link"' not in index_html

        for filename in [
            "standings.html", "statistics.html", "schedule-grid.html",
            "simulations.html", "team-bills.html",
        ]:
            html = zf.read(f"{root}/{filename}").decode("utf-8")
            assert 'href="index.html" class="mdn-back-link"' in html, f"{filename} missing back-to-index link"

    def test_season_data_card_on_every_page_including_team_pages(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        """Every page in the bundle -- index, all 4 section pages, and every
        team page -- gets the Season Data card at the top, with the "Game
        simulations" tile included since a simulation was supplied."""
        handler = FakeHandler("/api/export/bundle", server_with_games, body={"simulation_result": SAMPLE_SIM_RESULT})
        handler._handle_export_bundle()
        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))
        root = export._BUNDLE_ROOT

        for filename in [
            "index.html", "standings.html", "statistics.html",
            "schedule-grid.html", "simulations.html", "team-bills.html",
        ]:
            html = zf.read(f"{root}/{filename}").decode("utf-8")
            assert "Season data" in html, f"{filename} missing Season data card"
            assert "Game simulations" in html, f"{filename} missing Game simulations tile"

    def test_season_data_card_without_game_simulations_tile_when_no_simulation(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        """Without a simulation supplied, every page still gets the Season
        Data card (general season/cutoff context), just without the "Game
        simulations" tile."""
        handler = FakeHandler("/api/export/bundle", server_with_games, body={})
        handler._handle_export_bundle()
        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))
        root = export._BUNDLE_ROOT

        for filename in ["index.html", "standings.html", "team-bills.html"]:
            html = zf.read(f"{root}/{filename}").decode("utf-8")
            assert "Season data" in html, f"{filename} missing Season data card"
            assert "Game simulations" not in html

    def test_index_has_no_all_caps_export_heading(
        self, server_with_games: NFLSimulatorServer
    ) -> None:
        """The index page's nav bar carries the brand; it has no separate
        "... Export — <year>" <h1> heading."""
        handler = FakeHandler("/api/export/bundle", server_with_games, body={"simulation_result": SAMPLE_SIM_RESULT})
        handler._handle_export_bundle()
        zf = zipfile.ZipFile(BytesIO(handler.wfile.getvalue()))
        index_html = zf.read(f"{export._BUNDLE_ROOT}/index.html").decode("utf-8")

        assert "SIM Export —" not in index_html
        assert "<title>NFL Playoff Rankings Monte Carlo Simulator — 2026 Export</title>" in index_html
        assert "<h1" not in index_html
        assert "NFL PLAYOFF RANKINGS SIM" in index_html  # nav bar brand

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
