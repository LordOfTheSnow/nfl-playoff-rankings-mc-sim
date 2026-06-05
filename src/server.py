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
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from src.cache import Cache
from src.data_client import DataClient, FetchResult, GameStatus
from src.nfl_teams import ALL_TEAMS
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

            # Total expected games in a full NFL season: 272 (16 games per week × 17 weeks, but actually varies)
            # Use 272 as the standard regular season total
            expected_total = 272

            response = {
                "last_fetch_time": cache_status.get("last_fetch_time"),
                "games_cached": cache_status.get("games_cached", 0),
                "season_year": server.season_year,
                "completed": completed,
                "in_progress": in_progress,
                "scheduled": scheduled,
                "total_games": total,
                "expected_total": expected_total,
                "weeks_fetched": len(weeks_with_games),
                "weeks_with_games": weeks_with_games,
                "games_per_week": games_per_week,
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

            response = {
                "games_fetched": len(result.games),
                "warnings": result.warnings,
            }
            self._send_json_response(200, response)
        except Exception as e:
            logger.exception("Error fetching data")
            self._send_error_response(500, "ESPN API failure", str(e))

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
            )
            simulator = Simulator(config)
            result = simulator.run(games)

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
                """Sort division teams using simplified NFL tiebreaker order."""
                from src.data_client import GameStatus as GS

                # Group by win percentage
                from itertools import groupby

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
                        # Break ties using head-to-head among tied teams
                        team_names = [t["team"] for t in group]
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

                        # Determine which tiebreaker resolved the tie
                        h2h_wps = {}
                        for t in team_names:
                            hw, hl = h2h_records[t]
                            h2h_total = hw + hl
                            h2h_wps[t] = hw / h2h_total if h2h_total > 0 else 0.5

                        h2h_values = list(h2h_wps.values())
                        if len(set(h2h_values)) == len(h2h_values):
                            tiebreaker_label = "H2H"
                        else:
                            tiebreaker_label = "Conf"

                        # Sort by h2h win% desc, then conference record, then point diff, then alpha
                        def _tie_sort_key(td: dict[str, Any]) -> tuple:
                            t = td["team"]
                            hw, hl = h2h_records.get(t, (0, 0))
                            h2h_total = hw + hl
                            h2h_wp = hw / h2h_total if h2h_total > 0 else 0.5
                            cr = td["conference_record"].split("-")
                            cw, cl, ct = int(cr[0]), int(cr[1]), int(cr[2])
                            conf_total = cw + cl + ct
                            conf_wp = (cw + 0.5 * ct) / conf_total if conf_total > 0 else 0.0
                            ts = next((st for st in standings if st.team == t), None)
                            pf = ts.points_for or 0 if ts else 0
                            pa = ts.points_against or 0 if ts else 0
                            return (-h2h_wp, -conf_wp, -(pf - pa), t)

                        group.sort(key=_tie_sort_key)

                        # Annotate tied teams with tiebreaker info
                        for td in group:
                            t = td["team"]
                            hw, hl = h2h_records[t]
                            if tiebreaker_label == "H2H":
                                td["tiebreaker"] = f"H2H {hw}-{hl}"
                            else:
                                cr = td["conference_record"]
                                td["tiebreaker"] = f"Conf {cr}"

                        result.extend(group)

                return result

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
    ) -> None:
        """Initialize the server with configuration.

        Args:
            port: Port number to listen on (default 8080).
            season_year: NFL season year (default: current year).
            static_dir: Directory containing frontend static files (default "frontend").
        """
        if season_year is None:
            season_year = datetime.now().year

        self.season_year: int = season_year
        self.static_dir: str = static_dir
        self.cache: Cache = Cache()
        self.data_client: DataClient = DataClient(self.cache)

        server_address = ("", port)
        super().__init__(server_address, NFLRequestHandler)

    def start(self) -> None:
        """Start the HTTP server and print the local URL.

        Blocks until the server is shut down (e.g., via KeyboardInterrupt).
        """
        port = self.server_address[1]
        print(f"http://localhost:{port}")
        logger.info("NFL Simulator server started on port %d (season %d)", port, self.season_year)
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
    )
    server.start()


if __name__ == "__main__":
    main()
