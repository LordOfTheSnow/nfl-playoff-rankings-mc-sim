"""HTTP server and REST API for the NFL Monte Carlo Playoff Simulator.

Provides a local web server that serves the frontend static files and
exposes REST API endpoints for data fetching, simulation, standings,
and team schedule retrieval.

Runnable with: python -m src.server --port 8080 --season 2024

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from src.cache import Cache
from src.data_client import DataClient, FetchResult, Game, GameStatus
from src.nfl_teams import ALL_TEAMS, get_team_abbreviation
from src.simulator import SimulationConfig, Simulator, SimulationResult
from src.standings import compute_standings, determine_playoff_bracket

logger = logging.getLogger(__name__)


def _json_error(code: int, message: str, details: str = "") -> tuple[int, dict[str, Any]]:
    """Create a consistent JSON error response.

    Args:
        code: HTTP status code.
        message: Human-readable error description.
        details: Additional error details.

    Returns:
        Tuple of (status_code, error_dict).
    """
    return code, {
        "error": True,
        "message": message,
        "code": code,
        "details": details,
    }


def _serialize_simulation_result(result: SimulationResult) -> dict[str, Any]:
    """Serialize a SimulationResult to a JSON-compatible dictionary.

    Args:
        result: The simulation result to serialize.

    Returns:
        Dictionary suitable for JSON serialization.
    """
    team_results: list[dict[str, Any]] = []
    for team_name, tr in result.team_results.items():
        seed_probs: dict[str, float] = {}
        for seed, prob in tr.seed_distribution.items():
            seed_probs[str(seed)] = round(prob * 100, 1)

        team_results.append({
            "team": tr.team,
            "conference": tr.conference,
            "division": tr.division,
            "playoff_probability": round(tr.playoff_probability * 100, 1),
            "seed_probabilities": seed_probs,
            "strength_rating": round(tr.strength_rating, 4),
        })

    scenarios: list[dict[str, Any]] = []
    for scenario in result.scenarios:
        afc_seeds: list[str] = []
        nfc_seeds: list[str] = []
        for team, seed in sorted(scenario.bracket, key=lambda x: x[1]):
            # Determine conference for this team
            from src.nfl_teams import get_team_conference
            conf = get_team_conference(team)
            if conf == "AFC":
                afc_seeds.append(team)
            else:
                nfc_seeds.append(team)
        # Sort by seed within each conference
        afc_entries = [(t, s) for t, s in scenario.bracket if get_team_conference(t) == "AFC"]
        nfc_entries = [(t, s) for t, s in scenario.bracket if get_team_conference(t) == "NFC"]
        afc_seeds = [t for t, s in sorted(afc_entries, key=lambda x: x[1])]
        nfc_seeds = [t for t, s in sorted(nfc_entries, key=lambda x: x[1])]

        scenarios.append({
            "afc_seeds": afc_seeds,
            "nfc_seeds": nfc_seeds,
            "probability": round(scenario.probability * 100, 2),
        })

    team_strengths: dict[str, float] = {
        team: round(strength, 4)
        for team, strength in result.team_strengths.items()
    }

    return {
        "team_results": team_results,
        "top_scenarios": scenarios,
        "iterations_run": result.iterations_run,
        "cutoff_week_used": result.cutoff_week,
        "low_confidence": result.low_confidence,
        "convergence_achieved": True,
        "team_strengths": team_strengths,
        "fixed_games": result.fixed_games_count,
        "simulated_games": result.simulated_games_count,
    }


def _build_schedule_grid(games: list[Game], all_teams: list[str]) -> list[dict[str, Any]]:
    """Build schedule grid data from raw game list.

    Args:
        games: All games for a season (from cache).
        all_teams: List of all 32 team names.

    Returns:
        List of 32 team entries, each containing:
        - team: full team name (e.g., "Bills")
        - abbreviation: short ID (e.g., "BUF")
        - weeks: list of 18 entries (index 0 = week 1), each null for bye or:
          - opponent: abbreviation of opponent
          - home: boolean (true = home game)
          - status: "scheduled" | "in-progress" | "completed"
          - team_score: int | null
          - opponent_score: int | null
    """
    # Status mapping from GameStatus enum values to grid API values
    _STATUS_MAP: dict[str, str] = {
        GameStatus.SCHEDULED.value: "scheduled",
        GameStatus.IN_PROGRESS.value: "in-progress",
        GameStatus.COMPLETED.value: "completed",
    }

    # Statuses to skip (leave as null/bye)
    _SKIP_STATUSES = {GameStatus.POSTPONED, GameStatus.CANCELLED}

    # Initialize 32 team entries with 18-element weeks arrays (all null)
    grid: dict[str, dict[str, Any]] = {}
    for team in all_teams:
        abbr = get_team_abbreviation(team)
        grid[team] = {
            "team": team,
            "abbreviation": abbr,
            "weeks": [None] * 18,
        }

    # Populate grid from games
    for game in games:
        # Skip postponed/cancelled games
        if game.status in _SKIP_STATUSES:
            continue

        # Validate week is in range 1-18
        if game.week < 1 or game.week > 18:
            continue

        week_index = game.week - 1
        status = _STATUS_MAP.get(game.status.value)
        if status is None:
            continue

        home_abbr = get_team_abbreviation(game.home_team)
        away_abbr = get_team_abbreviation(game.away_team)

        # Populate from home team's perspective
        if game.home_team in grid:
            grid[game.home_team]["weeks"][week_index] = {
                "opponent": away_abbr,
                "home": True,
                "status": status,
                "team_score": game.home_score,
                "opponent_score": game.away_score,
            }

        # Populate from away team's perspective
        if game.away_team in grid:
            grid[game.away_team]["weeks"][week_index] = {
                "opponent": home_abbr,
                "home": False,
                "status": status,
                "team_score": game.away_score,
                "opponent_score": game.home_score,
            }

    # Sort team entries alphabetically by abbreviation
    entries = list(grid.values())
    entries.sort(key=lambda entry: entry["abbreviation"])
    return entries


class NFLRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the NFL Simulator REST API and static files.

    Handles API routes and serves static frontend files from the configured
    static directory.
    """

    # Suppress default access logging to stderr
    def log_message(self, format: str, *args: Any) -> None:
        """Log HTTP requests using the logging module instead of stderr."""
        logger.info(format, *args)

    def _send_json_response(self, status_code: int, data: dict[str, Any]) -> None:
        """Send a JSON response with appropriate headers.

        Args:
            status_code: HTTP status code.
            data: Dictionary to serialize as JSON.
        """
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_response(self, code: int, message: str, details: str = "") -> None:
        """Send a JSON error response.

        Args:
            code: HTTP status code.
            message: Human-readable error description.
            details: Additional error details.
        """
        _, error_body = _json_error(code, message, details)
        self._send_json_response(code, error_body)

    def _read_request_body(self) -> bytes:
        """Read the request body based on Content-Length header.

        Returns:
            The raw request body bytes.
        """
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            return self.rfile.read(content_length)
        return b""

    def _parse_json_body(self) -> dict[str, Any] | None:
        """Parse the request body as JSON.

        Returns:
            Parsed JSON dictionary, or None if body is empty or invalid.
        """
        body = self._read_request_body()
        if not body:
            return {}
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return None

    def do_GET(self) -> None:
        """Handle GET requests for API endpoints and static files."""
        path = unquote(self.path)

        # API routes
        if path == "/api/status":
            self._handle_get_status()
        elif path == "/api/standings":
            self._handle_get_standings()
        elif path == "/api/statistics":
            self._handle_get_statistics()
        elif path == "/api/schedule-grid":
            self._handle_get_schedule_grid()
        elif path.startswith("/api/clinch-estimate"):
            self._handle_get_clinch_estimate()
        elif path.startswith("/api/team/"):
            team_name = path[len("/api/team/"):]
            self._handle_get_team(team_name)
        elif path.startswith("/api/"):
            self._send_error_response(404, "Endpoint not found", f"No handler for GET {path}")
        else:
            self._serve_static_file(path)

    def do_POST(self) -> None:
        """Handle POST requests for API endpoints."""
        path = unquote(self.path)

        if path == "/api/fetch-data":
            self._handle_post_fetch_data()
        elif path == "/api/simulate":
            self._handle_post_simulate()
        elif path == "/api/clinching-scenarios":
            self._handle_post_clinching_scenarios()
        elif path == "/api/set-season":
            self._handle_post_set_season()
        elif path.startswith("/api/"):
            self._send_error_response(404, "Endpoint not found", f"No handler for POST {path}")
        else:
            self._send_error_response(405, "Method not allowed", "POST is only supported for API endpoints")

    def _handle_get_status(self) -> None:
        """Handle GET /api/status — return cache status."""
        server: NFLSimulatorServer = self.server  # type: ignore[assignment]
        try:
            cache_status = server.cache.get_cache_status()
            games = server.cache.get_games(server.season_year)

            # Compute game breakdown by status
            completed = sum(1 for g in games if g.status == GameStatus.COMPLETED)
            in_progress = sum(1 for g in games if g.status == GameStatus.IN_PROGRESS)
            scheduled = sum(1 for g in games if g.status == GameStatus.SCHEDULED)
            total = len(games)

            # Determine weeks with data
            weeks_with_games = sorted(set(g.week for g in games)) if games else []

            # Count games per week for the frontend
            games_per_week: dict[int, int] = {}
            for g in games:
                games_per_week[g.week] = games_per_week.get(g.week, 0) + 1

            # Count weeks where all games are completed
            completed_per_week: dict[int, int] = {}
            total_per_week: dict[int, int] = {}
            for g in games:
                total_per_week[g.week] = total_per_week.get(g.week, 0) + 1
                if g.status == GameStatus.COMPLETED:
                    completed_per_week[g.week] = completed_per_week.get(g.week, 0) + 1
            weeks_completed = sum(
                1 for w in total_per_week
                if completed_per_week.get(w, 0) == total_per_week[w]
            )

            # Total expected games in a full NFL season: 272 (16 games per week × 17 weeks, but actually varies)
            # Use 272 as the standard regular season total
            expected_total = 272

            response = {
                "version": server.version,
                "last_fetch_time": cache_status.get("last_fetch_time"),
                "games_cached": cache_status.get("games_cached", 0),
                "season_year": server.season_year,
                "completed": completed,
                "in_progress": in_progress,
                "scheduled": scheduled,
                "total_games": total,
                "expected_total": expected_total,
                "weeks_fetched": len(weeks_with_games),
                "weeks_completed": weeks_completed,
                "weeks_with_games": weeks_with_games,
                "games_per_week": games_per_week,
                "cpu_count": os.cpu_count() or 1,
            }
            self._send_json_response(200, response)
        except Exception as e:
            logger.exception("Error getting cache status")
            self._send_error_response(500, "Internal server error", str(e))

    def _handle_post_fetch_data(self) -> None:
        """Handle POST /api/fetch-data — trigger ESPN data fetch."""
        server: NFLSimulatorServer = self.server  # type: ignore[assignment]
        try:
            result: FetchResult = server.data_client.fetch_season_schedule(server.season_year)

            if result.errors:
                # ESPN API failures → 5xx
                self._send_error_response(
                    502,
                    "ESPN API error during data fetch",
                    "; ".join(result.errors),
                )
                return

            # Pre-compute weekly team strengths for all cutoff weeks
            self._compute_weekly_strengths(server)

            response = {
                "games_fetched": len(result.games),
                "warnings": result.warnings,
            }
            self._send_json_response(200, response)
        except Exception as e:
            logger.exception("Error fetching data")
            self._send_error_response(500, "ESPN API failure", str(e))

    def _handle_post_set_season(self) -> None:
        """Handle POST /api/set-season — change the active season year at runtime."""
        server: NFLSimulatorServer = self.server  # type: ignore[assignment]

        body = self._parse_json_body()
        if body is None:
            self._send_error_response(400, "Invalid JSON in request body", "")
            return

        season = body.get("season")
        if not isinstance(season, int) or season < 2000 or season > 2100:
            self._send_error_response(
                400,
                "Invalid season parameter",
                "season must be an integer between 2000 and 2100",
            )
            return

        server.season_year = season
        logger.info("Season changed to %d", season)
        self._send_json_response(200, {"season_year": season})

    def _handle_get_clinch_estimate(self) -> None:
        """Handle GET /api/clinch-estimate?team=<name> — preflight estimate."""
        server: NFLSimulatorServer = self.server  # type: ignore[assignment]

        # Parse query parameter
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        team_list = params.get("team", [])

        if not team_list or not team_list[0]:
            self._send_error_response(400, "Missing team parameter", "Usage: /api/clinch-estimate?team=Bills")
            return

        team = unquote(team_list[0])
        from src.nfl_teams import ALL_TEAMS
        if team not in ALL_TEAMS:
            self._send_error_response(400, "Invalid team name", f"Valid teams: {', '.join(sorted(ALL_TEAMS))}")
            return

        games = server.cache.get_games(server.season_year)
        if not games:
            self._send_error_response(409, "No cached data available", "Fetch data first.")
            return

        # Use cutoff_week from query param if provided, otherwise auto-detect
        cutoff_list = params.get("cutoff_week", [])
        if cutoff_list and cutoff_list[0]:
            try:
                cutoff_week = int(cutoff_list[0])
            except ValueError:
                cutoff_week = 0
        else:
            # Auto-detect: latest fully completed week
            completed_weeks = set()
            week_counts: dict[int, int] = {}
            week_completed: dict[int, int] = {}
            for g in games:
                week_counts[g.week] = week_counts.get(g.week, 0) + 1
                if g.status == GameStatus.COMPLETED:
                    week_completed[g.week] = week_completed.get(g.week, 0) + 1
            for w in week_counts:
                if week_completed.get(w, 0) == week_counts[w]:
                    completed_weeks.add(w)
            cutoff_week = max(completed_weeks) if completed_weeks else 0

        from src.clinching import estimate_clinching
        result = estimate_clinching(team, games, cutoff_week)
        result["cutoff_week"] = cutoff_week
        self._send_json_response(200, result)

    def _handle_post_clinching_scenarios(self) -> None:
        """Handle POST /api/clinching-scenarios — compute clinching scenarios for a team."""
        server: NFLSimulatorServer = self.server  # type: ignore[assignment]

        body = self._parse_json_body()
        if body is None:
            self._send_error_response(400, "Invalid JSON in request body", "")
            return

        team = body.get("team")
        from src.nfl_teams import ALL_TEAMS
        if not team or team not in ALL_TEAMS:
            self._send_error_response(400, "Invalid team name", f"Valid teams: {', '.join(sorted(ALL_TEAMS))}")
            return

        games = server.cache.get_games(server.season_year)
        if not games:
            self._send_error_response(409, "No cached data available", "Fetch data first.")
            return

        # Use cutoff_week from body if provided, otherwise auto-detect
        cutoff_week = body.get("cutoff_week")
        if cutoff_week is None:
            # Auto-detect: latest fully completed week
            week_counts: dict[int, int] = {}
            week_completed: dict[int, int] = {}
            for g in games:
                week_counts[g.week] = week_counts.get(g.week, 0) + 1
                if g.status == GameStatus.COMPLETED:
                    week_completed[g.week] = week_completed.get(g.week, 0) + 1
            completed_weeks = set()
            for w in week_counts:
                if week_completed.get(w, 0) == week_counts[w]:
                    completed_weeks.add(w)
            cutoff_week = max(completed_weeks) if completed_weeks else 0

        if not isinstance(cutoff_week, int) or cutoff_week < 14 or cutoff_week > 18:
            self._send_error_response(
                400,
                "Clinching scenarios are only available after week 14.",
                f"cutoff_week must be 14-18, got: {cutoff_week}",
            )
            return

        try:
            from src.clinching import compute_clinching_scenarios
            result = compute_clinching_scenarios(team, games, cutoff_week)

            if result.error:
                self._send_error_response(400, result.error, "")
                return

            # Serialize result
            response = self._serialize_clinching_result(result)
            response["cutoff_week"] = cutoff_week
            self._send_json_response(200, response)
        except Exception as e:
            logger.exception("Error computing clinching scenarios")
            self._send_error_response(500, "Clinching analysis error", str(e))

    def _serialize_clinching_result(self, result: Any) -> dict[str, Any]:
        """Serialize a ClinchingResult to a JSON-compatible dictionary."""
        record_groups = []
        for rg in result.record_groups:
            team_games = [
                {
                    "game_id": c.game_id,
                    "week": c.week,
                    "home_team": c.home_team,
                    "away_team": c.away_team,
                    "required_winner": c.required_winner,
                    "is_tie": c.is_tie,
                }
                for c in rg.team_games
            ]
            scenarios = []
            for s in rg.scenarios:
                conditions = [
                    {
                        "game_id": c.game_id,
                        "week": c.week,
                        "home_team": c.home_team,
                        "away_team": c.away_team,
                        "required_winner": c.required_winner,
                        "is_tie": c.is_tie,
                    }
                    for c in s.conditions
                ]
                scenarios.append({
                    "conditions": conditions,
                    "num_conditions": s.num_conditions,
                })
            record_groups.append({
                "wins": rg.wins,
                "losses": rg.losses,
                "ties": rg.ties,
                "team_games": team_games,
                "scenarios": scenarios,
                "no_path": rg.no_path,
            })

        return {
            "team": result.team,
            "record_groups": record_groups,
            "method": result.method,
            "exhaustive": result.exhaustive,
            "relevant_games_count": result.relevant_games_count,
            "contenders": result.contenders,
        }

    def _compute_weekly_strengths(self, server: "NFLSimulatorServer") -> None:
        """Pre-compute and store team strengths for each cutoff week (1-18).

        This allows the team schedule page to show opponent strength at the
        time of each game without recalculating on every page load.
        """
        from src.team_strength import TeamStrengthCalculator

        games = server.cache.get_games(server.season_year)
        if not games:
            return

        calculator = TeamStrengthCalculator()
        completed = [g for g in games if g.status == GameStatus.COMPLETED]

        for week in range(1, 19):
            week_games = [g for g in completed if g.week <= week]
            if not week_games:
                continue
            strengths = calculator.calculate(week_games)
            server.cache.store_weekly_strengths(server.season_year, week, strengths)

        logger.info("Pre-computed weekly strengths for weeks 1-18")

    def _handle_post_simulate(self) -> None:
        """Handle POST /api/simulate — run Monte Carlo simulation."""
        server: NFLSimulatorServer = self.server  # type: ignore[assignment]

        # Parse request body
        body = self._parse_json_body()
        if body is None:
            self._send_error_response(400, "Invalid JSON in request body", "Request body must be valid JSON")
            return

        # Extract and validate parameters
        iterations = body.get("iterations", 10000)
        cutoff_week = body.get("cutoff_week", None)
        noise = body.get("noise", 0.2)
        num_workers = body.get("num_workers", None)

        # Validate iterations
        if not isinstance(iterations, int) or iterations < 100 or iterations > 1_000_000:
            self._send_error_response(
                400,
                "Invalid iterations parameter",
                "iterations must be an integer between 100 and 1,000,000",
            )
            return

        # Validate cutoff_week
        if cutoff_week is not None:
            if not isinstance(cutoff_week, int) or cutoff_week < 1 or cutoff_week > 18:
                self._send_error_response(
                    400,
                    "Invalid cutoff_week parameter",
                    "cutoff_week must be an integer between 1 and 18",
                )
                return

        # Validate noise
        if not isinstance(noise, (int, float)) or noise < 0.0 or noise > 1.0:
            self._send_error_response(
                400,
                "Invalid noise parameter",
                "noise must be a number between 0.0 and 1.0",
            )
            return

        # Validate num_workers
        if num_workers is not None:
            if not isinstance(num_workers, int) or num_workers < 1:
                self._send_error_response(
                    400,
                    "Invalid num_workers parameter",
                    "num_workers must be a positive integer",
                )
                return

        # Check if cached data exists
        games = server.cache.get_games(server.season_year)
        if not games:
            self._send_error_response(
                409,
                "No cached data available",
                "Data must be fetched first using POST /api/fetch-data",
            )
            return

        # Run simulation
        try:
            config = SimulationConfig(
                iterations=iterations,
                cutoff_week=cutoff_week,
                noise=float(noise),
                num_workers=num_workers,
            )
            simulator = Simulator(config)

            import time
            t0 = time.perf_counter()
            result = simulator.run(games)
            elapsed = time.perf_counter() - t0
            logger.info(
                "Simulation completed: %d iterations, %d workers, %.2fs (%.1f iter/s)",
                iterations,
                num_workers or os.cpu_count() or 1,
                elapsed,
                iterations / elapsed if elapsed > 0 else 0,
            )

            response = _serialize_simulation_result(result)
            self._send_json_response(200, response)
        except ValueError as e:
            self._send_error_response(400, "Invalid simulation parameters", str(e))
        except Exception as e:
            logger.exception("Error running simulation")
            self._send_error_response(500, "Simulation error", str(e))

    def _handle_get_standings(self) -> None:
        """Handle GET /api/standings — compute and return current standings."""
        server: NFLSimulatorServer = self.server  # type: ignore[assignment]

        try:
            games = server.cache.get_games(server.season_year)
            if not games:
                self._send_error_response(
                    409,
                    "No cached data available",
                    "Data must be fetched first using POST /api/fetch-data",
                )
                return

            standings = compute_standings(games)
            bracket = determine_playoff_bracket(standings)

            # Compute team strengths from completed games
            from src.team_strength import TeamStrengthCalculator
            completed_games = [g for g in games if g.status == GameStatus.COMPLETED]
            calculator = TeamStrengthCalculator()
            team_strengths = calculator.calculate(completed_games)

            # Group standings by conference and division for the frontend
            conferences: dict[str, dict[str, list[dict[str, Any]]]] = {
                "AFC": {"East": [], "North": [], "South": [], "West": []},
                "NFC": {"East": [], "North": [], "South": [], "West": []},
            }

            for s in standings:
                team_data = {
                    "team": s.team,
                    "wins": s.wins,
                    "losses": s.losses,
                    "ties": s.ties,
                    "win_percentage": round(s.win_percentage, 3),
                    "games_behind": s.games_behind,
                    "strength": round(team_strengths.get(s.team, 1.0), 3),
                    "division_record": f"{s.division_record[0]}-{s.division_record[1]}-{s.division_record[2]}",
                    "conference_record": f"{s.conference_record[0]}-{s.conference_record[1]}-{s.conference_record[2]}",
                    "is_division_champion": s.is_division_champion,
                    "is_playoff_team": s.is_playoff_team,
                    "seed": s.seed,
                }
                conf = s.conference.value
                div = s.division.value
                if conf in conferences and div in conferences[conf]:
                    conferences[conf][div].append(team_data)

            # Sort teams within each division using tiebreaker-aware ordering.
            # For tied teams, compute head-to-head records within the division.
            def _division_tiebreak_sort(
                div_teams: list[dict[str, Any]],
            ) -> list[dict[str, Any]]:
                """Sort division teams using simplified NFL tiebreaker order.

                Tiebreaker steps (in order):
                1. H2H - Head-to-head record among tied teams
                2. Div - Division record
                3. Conf - Conference record
                4. SoV - Strength of victory (win% of teams beaten)
                5. SoS - Strength of schedule (win% of all opponents)
                6. Pts - Net points (points for minus points against)
                7. Alpha - Alphabetical (final fallback)
                """
                from src.data_client import GameStatus as GS

                # First sort by win% descending for grouping
                div_teams_sorted = sorted(
                    div_teams, key=lambda t: -t["win_percentage"]
                )

                result: list[dict[str, Any]] = []
                i = 0
                while i < len(div_teams_sorted):
                    # Find group of teams with same win%
                    wp = div_teams_sorted[i]["win_percentage"]
                    group = []
                    while i < len(div_teams_sorted) and div_teams_sorted[i]["win_percentage"] == wp:
                        group.append(div_teams_sorted[i])
                        i += 1

                    if len(group) == 1:
                        result.append(group[0])
                    else:
                        # Compute tiebreaker metrics for each tied team
                        team_names = [t["team"] for t in group]

                        # Step 1: Head-to-head records
                        h2h_records: dict[str, tuple[int, int]] = {}
                        for t in team_names:
                            wins = 0
                            losses = 0
                            for g in games:
                                if g.status != GS.COMPLETED:
                                    continue
                                if g.home_team == t and g.away_team in team_names:
                                    if g.home_score is not None and g.away_score is not None:
                                        if g.home_score > g.away_score:
                                            wins += 1
                                        elif g.home_score < g.away_score:
                                            losses += 1
                                elif g.away_team == t and g.home_team in team_names:
                                    if g.home_score is not None and g.away_score is not None:
                                        if g.away_score > g.home_score:
                                            wins += 1
                                        elif g.away_score < g.home_score:
                                            losses += 1
                            h2h_records[t] = (wins, losses)

                        h2h_wps: dict[str, float] = {}
                        for t in team_names:
                            hw, hl = h2h_records[t]
                            h2h_total = hw + hl
                            h2h_wps[t] = hw / h2h_total if h2h_total > 0 else 0.5

                        # Step 2: Division record win%
                        div_wps: dict[str, float] = {}
                        for td in group:
                            dr = td["division_record"].split("-")
                            dw, dl, dt = int(dr[0]), int(dr[1]), int(dr[2])
                            d_total = dw + dl + dt
                            div_wps[td["team"]] = (dw + 0.5 * dt) / d_total if d_total > 0 else 0.0

                        # Step 3: Conference record win%
                        conf_wps: dict[str, float] = {}
                        for td in group:
                            cr = td["conference_record"].split("-")
                            cw, cl, ct = int(cr[0]), int(cr[1]), int(cr[2])
                            c_total = cw + cl + ct
                            conf_wps[td["team"]] = (cw + 0.5 * ct) / c_total if c_total > 0 else 0.0

                        # Step 4: Strength of victory
                        sov: dict[str, float] = {}
                        for t in team_names:
                            beaten_teams: list[str] = []
                            for g in games:
                                if g.status != GS.COMPLETED:
                                    continue
                                if g.home_score is None or g.away_score is None:
                                    continue
                                if g.home_team == t and g.home_score > g.away_score:
                                    beaten_teams.append(g.away_team)
                                elif g.away_team == t and g.away_score > g.home_score:
                                    beaten_teams.append(g.home_team)
                            if beaten_teams:
                                beaten_wps = []
                                for bt in beaten_teams:
                                    bt_data = next((td for td in all_team_data if td["team"] == bt), None)
                                    if bt_data:
                                        beaten_wps.append(bt_data["win_percentage"])
                                sov[t] = sum(beaten_wps) / len(beaten_wps) if beaten_wps else 0.0
                            else:
                                sov[t] = 0.0

                        # Step 5: Strength of schedule
                        sos: dict[str, float] = {}
                        for t in team_names:
                            opp_teams: list[str] = []
                            for g in games:
                                if g.status != GS.COMPLETED:
                                    continue
                                if g.home_team == t:
                                    opp_teams.append(g.away_team)
                                elif g.away_team == t:
                                    opp_teams.append(g.home_team)
                            if opp_teams:
                                opp_wps = []
                                for ot in opp_teams:
                                    ot_data = next((td for td in all_team_data if td["team"] == ot), None)
                                    if ot_data:
                                        opp_wps.append(ot_data["win_percentage"])
                                sos[t] = sum(opp_wps) / len(opp_wps) if opp_wps else 0.0
                            else:
                                sos[t] = 0.0

                        # Step 6: Net points
                        net_pts: dict[str, int] = {}
                        for t in team_names:
                            ts = next((st for st in standings if st.team == t), None)
                            pf = ts.points_for or 0 if ts else 0
                            pa = ts.points_against or 0 if ts else 0
                            net_pts[t] = pf - pa

                        # Determine which step actually breaks the tie
                        def _values_differentiate(vals: dict[str, float | int]) -> bool:
                            """Check if values produce a unique ordering (no ties)."""
                            v_list = list(vals.values())
                            return len(set(v_list)) == len(v_list)

                        if _values_differentiate(h2h_wps):
                            tiebreaker_label = "H2H"
                        elif _values_differentiate(div_wps):
                            tiebreaker_label = "Div"
                        elif _values_differentiate(conf_wps):
                            tiebreaker_label = "Conf"
                        elif _values_differentiate(sov):
                            tiebreaker_label = "SoV"
                        elif _values_differentiate(sos):
                            tiebreaker_label = "SoS"
                        elif _values_differentiate(net_pts):
                            tiebreaker_label = "Pts"
                        else:
                            tiebreaker_label = "Alpha"

                        # Sort using all steps as a composite key
                        def _tie_sort_key(td: dict[str, Any]) -> tuple:
                            t = td["team"]
                            return (
                                -h2h_wps[t],
                                -div_wps[t],
                                -conf_wps[t],
                                -sov[t],
                                -sos[t],
                                -net_pts[t],
                                t,  # alphabetical fallback
                            )

                        group.sort(key=_tie_sort_key)

                        # Annotate tied teams with tiebreaker info
                        for td in group:
                            t = td["team"]
                            hw, hl = h2h_records[t]
                            if tiebreaker_label == "H2H":
                                td["tiebreaker"] = f"H2H {hw}-{hl}"
                            elif tiebreaker_label == "Div":
                                td["tiebreaker"] = f"Div {td['division_record']}"
                            elif tiebreaker_label == "Conf":
                                td["tiebreaker"] = f"Conf {td['conference_record']}"
                            elif tiebreaker_label == "SoV":
                                td["tiebreaker"] = f"SoV {sov[t]:.3f}"
                            elif tiebreaker_label == "SoS":
                                td["tiebreaker"] = f"SoS {sos[t]:.3f}"
                            elif tiebreaker_label == "Pts":
                                sign = "+" if net_pts[t] > 0 else ""
                                td["tiebreaker"] = f"Pts {sign}{net_pts[t]}"
                            else:
                                td["tiebreaker"] = "Alpha"

                        result.extend(group)

                return result

            # Build flat list of all team data for SoV/SoS lookups
            all_team_data: list[dict[str, Any]] = []
            for conf_name in conferences:
                for div_name in conferences[conf_name]:
                    all_team_data.extend(conferences[conf_name][div_name])

            for conf_name in conferences:
                for div_name in conferences[conf_name]:
                    conferences[conf_name][div_name] = _division_tiebreak_sort(
                        conferences[conf_name][div_name]
                    )

            # Serialize bracket
            bracket_data: dict[str, Any] = {
                "afc_seeds": [
                    {"team": s.team, "seed": s.seed} for s in bracket.afc_seeds
                ],
                "nfc_seeds": [
                    {"team": s.team, "seed": s.seed} for s in bracket.nfc_seeds
                ],
            }

            response = {
                "conferences": conferences,
                "bracket": bracket_data,
                "last_updated": datetime.utcnow().isoformat() + "Z",
            }
            self._send_json_response(200, response)
        except Exception as e:
            logger.exception("Error computing standings")
            self._send_error_response(500, "Error computing standings", str(e))

    def _handle_get_schedule_grid(self) -> None:
        """Handle GET /api/schedule-grid — return league-wide schedule grid data."""
        server: NFLSimulatorServer = self.server  # type: ignore[assignment]

        try:
            games = server.cache.get_games(server.season_year)
            if not games:
                self._send_error_response(404, "No schedule data available.")
                return

            grid = _build_schedule_grid(games, list(ALL_TEAMS))
            self._send_json_response(200, {"teams": grid})
        except Exception as e:
            logger.exception("Error building schedule grid")
            self._send_error_response(500, "Internal server error", str(e))

    def _handle_get_statistics(self) -> None:
        """Handle GET /api/statistics — return season-wide statistics."""
        server: NFLSimulatorServer = self.server  # type: ignore[assignment]

        try:
            games = server.cache.get_games(server.season_year)
            if not games:
                self._send_error_response(
                    409,
                    "No cached data available",
                    "Data must be fetched first using POST /api/fetch-data",
                )
                return

            completed = [g for g in games if g.status == GameStatus.COMPLETED
                         and g.home_score is not None and g.away_score is not None]

            total_games = len(completed)
            home_wins = 0
            away_wins = 0
            ties = 0
            total_points = 0
            total_winner_points = 0
            total_loser_points = 0
            decided_games = 0

            for g in completed:
                total_points += (g.home_score or 0) + (g.away_score or 0)
                if g.home_score > g.away_score:
                    home_wins += 1
                    total_winner_points += g.home_score
                    total_loser_points += g.away_score
                    decided_games += 1
                elif g.away_score > g.home_score:
                    away_wins += 1
                    total_winner_points += g.away_score
                    total_loser_points += g.home_score
                    decided_games += 1
                else:
                    ties += 1

            avg_winner_score = total_winner_points / decided_games if decided_games > 0 else 0.0
            avg_loser_score = total_loser_points / decided_games if decided_games > 0 else 0.0

            # Count overtime games (period > 4)
            overtime_games = sum(1 for g in completed if g.quarter is not None and g.quarter > 4)

            # Count one-score games (point differential <= 8)
            one_score_games = sum(1 for g in completed if abs(g.home_score - g.away_score) <= 8)

            # Compute streaks per team
            from src.nfl_teams import ALL_TEAMS

            longest_win_streak = {"team": "", "streak": 0, "from_week": 0, "to_week": 0}
            longest_lose_streak = {"team": "", "streak": 0, "from_week": 0, "to_week": 0}

            for team in ALL_TEAMS:
                team_games = sorted(
                    [g for g in completed if g.home_team == team or g.away_team == team],
                    key=lambda g: (g.week, g.date),
                )

                win_streak = 0
                lose_streak = 0
                max_win = 0
                max_lose = 0
                win_start_week = 0
                win_end_week = 0
                lose_start_week = 0
                lose_end_week = 0
                cur_win_start = 0
                cur_lose_start = 0

                for g in team_games:
                    is_home = g.home_team == team
                    if is_home:
                        team_won = g.home_score > g.away_score
                        team_lost = g.home_score < g.away_score
                    else:
                        team_won = g.away_score > g.home_score
                        team_lost = g.away_score < g.home_score

                    if team_won:
                        if win_streak == 0:
                            cur_win_start = g.week
                        win_streak += 1
                        lose_streak = 0
                        if win_streak > max_win:
                            max_win = win_streak
                            win_start_week = cur_win_start
                            win_end_week = g.week
                    elif team_lost:
                        if lose_streak == 0:
                            cur_lose_start = g.week
                        lose_streak += 1
                        win_streak = 0
                        if lose_streak > max_lose:
                            max_lose = lose_streak
                            lose_start_week = cur_lose_start
                            lose_end_week = g.week
                    else:
                        win_streak = 0
                        lose_streak = 0

                if max_win > longest_win_streak["streak"]:
                    longest_win_streak = {"team": team, "streak": max_win, "from_week": win_start_week, "to_week": win_end_week}
                if max_lose > longest_lose_streak["streak"]:
                    longest_lose_streak = {"team": team, "streak": max_lose, "from_week": lose_start_week, "to_week": lose_end_week}

            response = {
                "total_games": total_games,
                "home_wins": home_wins,
                "home_wins_pct": round(home_wins / total_games * 100, 1) if total_games > 0 else 0,
                "away_wins": away_wins,
                "away_wins_pct": round(away_wins / total_games * 100, 1) if total_games > 0 else 0,
                "ties": ties,
                "ties_pct": round(ties / total_games * 100, 1) if total_games > 0 else 0,
                "avg_winner_score": round(avg_winner_score),
                "avg_loser_score": round(avg_loser_score),
                "overtime_games": overtime_games,
                "overtime_pct": round(overtime_games / total_games * 100, 1) if total_games > 0 else 0,
                "one_score_games": one_score_games,
                "one_score_pct": round(one_score_games / total_games * 100, 1) if total_games > 0 else 0,
                "longest_win_streak": longest_win_streak,
                "longest_lose_streak": longest_lose_streak,
            }
            self._send_json_response(200, response)
        except Exception as e:
            logger.exception("Error computing statistics")
            self._send_error_response(500, "Error computing statistics", str(e))

    def _handle_get_team(self, team_name: str) -> None:
        """Handle GET /api/team/<name> — return team schedule.

        Args:
            team_name: The team name from the URL path.
        """
        server: NFLSimulatorServer = self.server  # type: ignore[assignment]

        # Validate team name
        if team_name not in ALL_TEAMS:
            self._send_error_response(
                400,
                f"Unknown team: {team_name}",
                f"Valid teams are: {', '.join(sorted(ALL_TEAMS))}",
            )
            return

        try:
            games = server.cache.get_team_games(server.season_year, team_name)

            # Load pre-computed weekly strengths
            weekly_strengths = server.cache.get_weekly_strengths(server.season_year)

            # Compute record
            wins = 0
            losses = 0
            ties = 0
            for game in games:
                if game.status != GameStatus.COMPLETED:
                    continue
                if game.home_score is None or game.away_score is None:
                    continue
                is_home = game.home_team == team_name
                if game.home_score == game.away_score:
                    ties += 1
                elif is_home and game.home_score > game.away_score:
                    wins += 1
                elif not is_home and game.away_score > game.home_score:
                    wins += 1
                else:
                    losses += 1

            # Serialize games
            games_list: list[dict[str, Any]] = []
            for game in sorted(games, key=lambda g: g.week):
                is_home = game.home_team == team_name
                opponent = game.away_team if is_home else game.home_team

                game_data: dict[str, Any] = {
                    "week": game.week,
                    "opponent": opponent,
                    "home": is_home,
                    "status": game.status.value,
                    "date": game.date.isoformat(),
                }

                # Add opponent strength at that point in the season
                week_strengths = weekly_strengths.get(game.week, {})
                opp_strength = week_strengths.get(opponent)
                if opp_strength is not None:
                    game_data["opponent_strength"] = round(opp_strength, 3)

                # Add team's own strength at that point in the season
                team_strength = week_strengths.get(team_name)
                if team_strength is not None:
                    game_data["team_strength"] = round(team_strength, 3)

                if game.status == GameStatus.COMPLETED:
                    game_data["home_score"] = game.home_score
                    game_data["away_score"] = game.away_score
                    # Determine result
                    if game.home_score is not None and game.away_score is not None:
                        if game.home_score == game.away_score:
                            game_data["result"] = "tie"
                        elif (is_home and game.home_score > game.away_score) or \
                             (not is_home and game.away_score > game.home_score):
                            game_data["result"] = "win"
                        else:
                            game_data["result"] = "loss"

                elif game.status == GameStatus.IN_PROGRESS:
                    game_data["home_score"] = game.home_score
                    game_data["away_score"] = game.away_score
                    game_data["quarter"] = game.quarter
                    game_data["clock"] = game.clock

                games_list.append(game_data)

            total = wins + losses + ties
            win_percentage = (wins + 0.5 * ties) / total if total > 0 else 0.0

            response = {
                "team": team_name,
                "games": games_list,
                "record": {
                    "wins": wins,
                    "losses": losses,
                    "ties": ties,
                    "win_percentage": round(win_percentage, 3),
                },
            }
            self._send_json_response(200, response)
        except Exception as e:
            logger.exception("Error getting team schedule")
            self._send_error_response(500, "Error retrieving team schedule", str(e))

    def _serve_static_file(self, path: str) -> None:
        """Serve a static file from the configured static directory.

        Maps / to index.html. Sets appropriate Content-Type headers.

        Args:
            path: The URL path requested.
        """
        server: NFLSimulatorServer = self.server  # type: ignore[assignment]

        # Map / to index.html
        if path == "/" or path == "":
            path = "/index.html"

        # Strip query parameters (e.g., ?v=2 for cache busting)
        if "?" in path:
            path = path.split("?")[0]

        # Resolve the file path relative to static_dir
        # Prevent directory traversal
        clean_path = path.lstrip("/")
        file_path = Path(server.static_dir) / clean_path

        # Security: ensure the resolved path is within static_dir
        try:
            resolved = file_path.resolve()
            static_resolved = Path(server.static_dir).resolve()
            if not str(resolved).startswith(str(static_resolved)):
                self._send_error_response(403, "Forbidden", "Access denied")
                return
        except (OSError, ValueError):
            self._send_error_response(400, "Invalid path", "")
            return

        if not file_path.is_file():
            self._send_error_response(404, "File not found", f"No such file: {clean_path}")
            return

        # Determine content type
        content_type = self._get_content_type(str(file_path))

        try:
            with open(file_path, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except OSError as e:
            self._send_error_response(500, "Error reading file", str(e))

    @staticmethod
    def _get_content_type(file_path: str) -> str:
        """Determine the Content-Type for a file based on its extension.

        Args:
            file_path: Path to the file.

        Returns:
            MIME type string.
        """
        extension_map: dict[str, str] = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }

        ext = Path(file_path).suffix.lower()
        if ext in extension_map:
            return extension_map[ext]

        # Fallback to mimetypes module
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"


class NFLSimulatorServer(HTTPServer):
    """HTTP server for the NFL Monte Carlo Playoff Simulator.

    Extends HTTPServer to hold shared application state (cache, data client,
    season year, static directory path) accessible to request handlers.
    """

    def __init__(
        self,
        port: int = 8080,
        season_year: int | None = None,
        static_dir: str = "frontend",
        db_path: str = "nfl_cache.db",
    ) -> None:
        """Initialize the server with configuration.

        Args:
            port: Port number to listen on (default 8080).
            season_year: NFL season year (default: current year).
            static_dir: Directory containing frontend static files (default "frontend").
            db_path: Path to the SQLite cache database file (default "nfl_cache.db").
        """
        if season_year is None:
            season_year = datetime.now().year

        self.season_year: int = season_year
        self.static_dir: str = static_dir
        self.cache: Cache = Cache(db_path=db_path)
        self.data_client: DataClient = DataClient(self.cache)

        # Read version from package metadata
        try:
            from importlib.metadata import version
            self.version: str = version("nfl-monte-carlo-simulator")
        except Exception:
            self.version = "unknown"

        server_address = ("", port)
        super().__init__(server_address, NFLRequestHandler)

    def start(self) -> None:
        """Start the HTTP server and print the local URL.

        Blocks until the server is shut down (e.g., via KeyboardInterrupt).
        """
        port = self.server_address[1]
        print(f"http://localhost:{port}")
        logger.info("NFL Playoff Ranking Simulator server v%s started on port %d (season %d)", self.version, port, self.season_year)
        try:
            self.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
        finally:
            self.server_close()
            self.cache.close()
            self.data_client.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the server.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="python -m src.server",
        description="NFL Monte Carlo Playoff Simulator — local web server",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port number to listen on (default: 8080)",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=datetime.now().year,
        help=f"NFL season year (default: {datetime.now().year})",
    )
    parser.add_argument(
        "--static-dir",
        type=str,
        default="frontend",
        help="Directory containing frontend static files (default: frontend)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="nfl_cache.db",
        help="Path to the SQLite cache database file (default: nfl_cache.db)",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the server.

    Parses CLI arguments and starts the HTTP server.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        args = parse_args(argv)
    except SystemExit as e:
        # argparse calls sys.exit on error — re-raise to propagate non-zero exit
        raise

    server = NFLSimulatorServer(
        port=args.port,
        season_year=args.season,
        static_dir=args.static_dir,
        db_path=args.db_path,
    )
    server.start()


if __name__ == "__main__":
    main()
