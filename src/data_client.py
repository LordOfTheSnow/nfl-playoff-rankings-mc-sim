"""Data client for fetching NFL data from ESPN's public JSON API.

ESPN endpoints used:
- Scoreboard: site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard
- Standings: site.api.espn.com/apis/v2/sports/football/nfl/standings
- Teams: site.api.espn.com/apis/site/v2/sports/football/nfl/teams
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

import httpx

from src.cache import Cache
from src.nfl_teams import ALL_TEAMS

logger = logging.getLogger(__name__)

# ESPN scoreboard base URL
ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
)

# Mapping from ESPN status type names to our GameStatus enum
_ESPN_STATUS_MAP: dict[str, str] = {
    "STATUS_SCHEDULED": "scheduled",
    "STATUS_IN_PROGRESS": "in-progress",
    "STATUS_FINAL": "completed",
    "STATUS_POSTPONED": "postponed",
    "STATUS_CANCELED": "cancelled",
}

# Mapping from ESPN full display names to our short team names
# ESPN uses full names like "Kansas City Chiefs", we use "Chiefs"
_ESPN_DISPLAY_NAME_TO_SHORT: dict[str, str] = {
    "Arizona Cardinals": "Cardinals",
    "Atlanta Falcons": "Falcons",
    "Baltimore Ravens": "Ravens",
    "Buffalo Bills": "Bills",
    "Carolina Panthers": "Panthers",
    "Chicago Bears": "Bears",
    "Cincinnati Bengals": "Bengals",
    "Cleveland Browns": "Browns",
    "Dallas Cowboys": "Cowboys",
    "Denver Broncos": "Broncos",
    "Detroit Lions": "Lions",
    "Green Bay Packers": "Packers",
    "Houston Texans": "Texans",
    "Indianapolis Colts": "Colts",
    "Jacksonville Jaguars": "Jaguars",
    "Kansas City Chiefs": "Chiefs",
    "Las Vegas Raiders": "Raiders",
    "Los Angeles Chargers": "Chargers",
    "Los Angeles Rams": "Rams",
    "Miami Dolphins": "Dolphins",
    "Minnesota Vikings": "Vikings",
    "New England Patriots": "Patriots",
    "New Orleans Saints": "Saints",
    "New York Giants": "Giants",
    "New York Jets": "Jets",
    "Philadelphia Eagles": "Eagles",
    "Pittsburgh Steelers": "Steelers",
    "San Francisco 49ers": "49ers",
    "Seattle Seahawks": "Seahawks",
    "Tampa Bay Buccaneers": "Buccaneers",
    "Tennessee Titans": "Titans",
    "Washington Commanders": "Commanders",
}


class GameStatus(Enum):
    """Status of an NFL game."""

    SCHEDULED = "scheduled"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Game:
    """Represents a single NFL game with all relevant data.

    Frozen dataclass to ensure immutability — game data should not be
    modified after creation.
    """

    game_id: str
    week: int
    date: date
    home_team: str
    away_team: str
    status: GameStatus
    home_score: int | None = None  # None if not completed/in-progress
    away_score: int | None = None  # None if not completed/in-progress
    home_points: int | None = None  # Points scored (for tiebreakers)
    away_points: int | None = None  # Points scored (for tiebreakers)
    quarter: int | None = None  # Current quarter for in-progress games
    clock: str | None = None  # Game clock for in-progress games (e.g., "5:32")


@dataclass
class FetchResult:
    """Result of a data fetch operation.

    Contains the fetched games along with any warnings (partial failures)
    and errors (complete failures) encountered during the fetch.
    """

    games: list[Game] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ESPNSchemaError(Exception):
    """Raised when the ESPN API response is missing required fields."""

    def __init__(self, field_name: str, context: str = "") -> None:
        self.field_name = field_name
        self.context = context
        msg = f"ESPN schema error: required field '{field_name}' is missing"
        if context:
            msg += f" (in {context})"
        super().__init__(msg)


def _resolve_team_name(display_name: str) -> str:
    """Convert ESPN full display name to our short team name.

    Tries the full mapping first, then falls back to extracting the last
    word of the display name (works for most teams like "Kansas City Chiefs" → "Chiefs").

    Args:
        display_name: ESPN team display name (e.g., "Kansas City Chiefs").

    Returns:
        Short team name (e.g., "Chiefs").
    """
    if display_name in _ESPN_DISPLAY_NAME_TO_SHORT:
        return _ESPN_DISPLAY_NAME_TO_SHORT[display_name]

    # Fallback: use last word of display name
    short_name = display_name.split()[-1] if display_name else display_name

    # Special case for "49ers" — the display name is "San Francisco 49ers"
    # which the last-word approach handles correctly

    # Verify it's a known team
    if short_name in ALL_TEAMS:
        return short_name

    # If we can't resolve, return the display name as-is and log a warning
    logger.warning(
        "Could not resolve ESPN team name '%s' to a known team", display_name
    )
    return display_name


def parse_espn_event(event: dict[str, Any]) -> Game:
    """Parse a single ESPN event (game) JSON object into a Game dataclass.

    Args:
        event: A dictionary from the ESPN scoreboard response's "events" array.

    Returns:
        A Game object with all extracted fields.

    Raises:
        ESPNSchemaError: If a required field is missing from the JSON.
    """
    # Extract game_id
    if "id" not in event:
        raise ESPNSchemaError("id", "event")
    game_id = str(event["id"])

    # Extract date
    if "date" not in event:
        raise ESPNSchemaError("date", "event")
    date_str = event["date"]
    # ESPN dates are ISO 8601 with time, e.g., "2024-09-05T20:20Z"
    # We only need the date portion
    game_date = date.fromisoformat(date_str[:10])

    # Extract week number
    if "week" not in event:
        raise ESPNSchemaError("week", "event")
    week_obj = event["week"]
    if not isinstance(week_obj, dict) or "number" not in week_obj:
        raise ESPNSchemaError("week.number", "event")
    week_number = int(week_obj["number"])

    # Extract status
    if "status" not in event:
        raise ESPNSchemaError("status", "event")
    status_obj = event["status"]
    if not isinstance(status_obj, dict) or "type" not in status_obj:
        raise ESPNSchemaError("status.type", "event")
    status_type = status_obj["type"]
    if not isinstance(status_type, dict) or "name" not in status_type:
        raise ESPNSchemaError("status.type.name", "event")

    espn_status_name = status_type["name"]
    if espn_status_name not in _ESPN_STATUS_MAP:
        raise ESPNSchemaError(
            "status.type.name",
            f"event (unknown status: '{espn_status_name}')",
        )
    game_status = GameStatus(_ESPN_STATUS_MAP[espn_status_name])

    # Extract quarter/period — for in-progress (current quarter) and completed (final period, to detect OT)
    quarter: int | None = None
    clock: str | None = None
    period = status_obj.get("period")
    if period is not None:
        quarter = int(period)
    if game_status == GameStatus.IN_PROGRESS:
        display_clock = status_obj.get("displayClock")
        if display_clock is not None:
            clock = str(display_clock)

    # Extract competitions and competitors
    if "competitions" not in event:
        raise ESPNSchemaError("competitions", "event")
    competitions = event["competitions"]
    if not competitions or not isinstance(competitions, list):
        raise ESPNSchemaError("competitions[0]", "event")

    competition = competitions[0]
    if "competitors" not in competition:
        raise ESPNSchemaError("competitions[0].competitors", "event")
    competitors = competition["competitors"]
    if not competitors or not isinstance(competitors, list) or len(competitors) < 2:
        raise ESPNSchemaError(
            "competitions[0].competitors", "event (expected at least 2 competitors)"
        )

    # Parse competitors — find home and away
    home_team: str | None = None
    away_team: str | None = None
    home_score: int | None = None
    away_score: int | None = None

    for competitor in competitors:
        if "homeAway" not in competitor:
            raise ESPNSchemaError("competitions[0].competitors[].homeAway", "event")

        # Extract team name
        if "team" not in competitor:
            raise ESPNSchemaError("competitions[0].competitors[].team", "event")
        team_obj = competitor["team"]
        if "displayName" not in team_obj:
            raise ESPNSchemaError(
                "competitions[0].competitors[].team.displayName", "event"
            )
        display_name = team_obj["displayName"]
        team_name = _resolve_team_name(display_name)

        # Extract score (ESPN returns as string)
        score: int | None = None
        if "score" in competitor and competitor["score"] is not None:
            try:
                score = int(competitor["score"])
            except (ValueError, TypeError):
                score = None

        if competitor["homeAway"] == "home":
            home_team = team_name
            home_score = score
        elif competitor["homeAway"] == "away":
            away_team = team_name
            away_score = score

    if home_team is None:
        raise ESPNSchemaError("home competitor", "event (no home team found)")
    if away_team is None:
        raise ESPNSchemaError("away competitor", "event (no away team found)")

    # For completed and in-progress games, scores are also points
    home_points: int | None = None
    away_points: int | None = None
    if game_status in (GameStatus.COMPLETED, GameStatus.IN_PROGRESS):
        home_points = home_score
        away_points = away_score

    return Game(
        game_id=game_id,
        week=week_number,
        date=game_date,
        home_team=home_team,
        away_team=away_team,
        status=game_status,
        home_score=home_score if game_status in (GameStatus.COMPLETED, GameStatus.IN_PROGRESS) else None,
        away_score=away_score if game_status in (GameStatus.COMPLETED, GameStatus.IN_PROGRESS) else None,
        home_points=home_points,
        away_points=away_points,
        quarter=quarter,
        clock=clock,
    )


def parse_espn_scoreboard(response_json: dict[str, Any]) -> list[Game]:
    """Parse a complete ESPN scoreboard API response into a list of Game objects.

    Args:
        response_json: The full JSON response from the ESPN scoreboard endpoint.

    Returns:
        List of Game objects parsed from the response.

    Raises:
        ESPNSchemaError: If the response structure is invalid or missing required fields.
    """
    if "events" not in response_json:
        raise ESPNSchemaError("events", "scoreboard response")

    events = response_json["events"]
    if not isinstance(events, list):
        raise ESPNSchemaError("events", "scoreboard response (expected array)")

    games: list[Game] = []
    for event in events:
        games.append(parse_espn_event(event))

    return games


class DataClient:
    """Fetches NFL data from ESPN's public JSON API.

    ESPN endpoints used:
    - Scoreboard: site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard
    - Standings: site.api.espn.com/apis/v2/sports/football/nfl/standings
    - Teams: site.api.espn.com/apis/site/v2/sports/football/nfl/teams

    No authentication is required for these public endpoints.
    """

    def __init__(self, cache: Cache, timeout: int = 30) -> None:
        """Initialize the data client.

        Args:
            cache: Cache instance for storing/retrieving fetched data.
            timeout: HTTP request timeout in seconds (default: 30).
        """
        self._cache = cache
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def _fetch_week(self, year: int, week: int) -> list[Game]:
        """Fetch games for a specific week from ESPN.

        Args:
            year: The NFL season year.
            week: The week number (1-18).

        Returns:
            List of Game objects for the specified week.

        Raises:
            httpx.HTTPStatusError: If the API returns a non-success status code.
            httpx.TimeoutException: If the request times out.
            ESPNSchemaError: If the response schema is unexpected.
        """
        url = ESPN_SCOREBOARD_URL
        params = {
            "week": str(week),
            "seasontype": "2",
            "dates": str(year),
        }

        response = self._client.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        return parse_espn_scoreboard(data)

    def fetch_season_schedule(self, year: int) -> FetchResult:
        """Fetch the complete NFL regular season schedule for a given year.

        Fetches weeks 1-18 from the ESPN scoreboard API. If some weeks
        fail, returns successfully fetched games with warnings indicating
        which weeks could not be retrieved.

        Args:
            year: The NFL season year (e.g., 2024).

        Returns:
            FetchResult containing games, warnings, and errors.
        """
        result = FetchResult()
        failed_weeks: list[int] = []

        for week in range(1, 19):
            # Check cache freshness first
            if self._cache.is_fresh(year, week):
                cached_games = self._cache.get_games(year, week)
                if cached_games:
                    result.games.extend(cached_games)
                    continue

            try:
                games = self._fetch_week(year, week)
                result.games.extend(games)
                # Store in cache
                if games:
                    self._cache.store_games(games, year)
            except httpx.TimeoutException:
                failed_weeks.append(week)
                warning_msg = (
                    f"Could not fetch week {week}: request timed out after "
                    f"{self._timeout}s (URL: {ESPN_SCOREBOARD_URL})"
                )
                result.warnings.append(warning_msg)
                logger.warning(warning_msg)
                # Try to return stale cached data for this week
                stale_games = self._cache.get_games(year, week)
                if stale_games:
                    result.games.extend(stale_games)
                    warnings.warn(
                        f"Using stale cached data for week {week}",
                        stacklevel=2,
                    )
            except httpx.HTTPStatusError as e:
                failed_weeks.append(week)
                warning_msg = (
                    f"Could not fetch week {week}: HTTP {e.response.status_code} "
                    f"(URL: {e.request.url})"
                )
                result.warnings.append(warning_msg)
                logger.warning(warning_msg)
                # Try to return stale cached data for this week
                stale_games = self._cache.get_games(year, week)
                if stale_games:
                    result.games.extend(stale_games)
            except ESPNSchemaError as e:
                failed_weeks.append(week)
                error_msg = f"Schema error fetching week {week}: {e}"
                result.errors.append(error_msg)
                logger.error(error_msg)
            except httpx.RequestError as e:
                failed_weeks.append(week)
                warning_msg = (
                    f"Could not fetch week {week}: network error ({e}) "
                    f"(URL: {ESPN_SCOREBOARD_URL})"
                )
                result.warnings.append(warning_msg)
                logger.warning(warning_msg)
                # Try to return stale cached data for this week
                stale_games = self._cache.get_games(year, week)
                if stale_games:
                    result.games.extend(stale_games)

        if failed_weeks:
            count = len(failed_weeks)
            summary = f"{count} week(s) could not be retrieved: {failed_weeks}"
            if summary not in result.warnings:
                result.warnings.append(summary)

        return result

    def fetch_week_results(self, year: int, week: int) -> FetchResult:
        """Fetch game results for a specific week.

        Args:
            year: The NFL season year (e.g., 2024).
            week: The week number (1-18).

        Returns:
            FetchResult containing games, warnings, and errors.
        """
        result = FetchResult()

        # Check cache freshness first
        if self._cache.is_fresh(year, week):
            cached_games = self._cache.get_games(year, week)
            if cached_games:
                result.games = cached_games
                return result

        try:
            games = self._fetch_week(year, week)
            result.games = games
            # Store in cache
            if games:
                self._cache.store_games(games, year)
        except httpx.TimeoutException:
            error_msg = (
                f"Failed to fetch week {week} results: request timed out after "
                f"{self._timeout}s (URL: {ESPN_SCOREBOARD_URL})"
            )
            result.errors.append(error_msg)
            logger.error(error_msg)
            # Return stale cached data if available
            stale_games = self._cache.get_games(year, week)
            if stale_games:
                result.games = stale_games
                result.warnings.append(
                    f"Returning stale cached data for week {week} due to network failure"
                )
        except httpx.HTTPStatusError as e:
            error_msg = (
                f"Failed to fetch week {week} results: HTTP {e.response.status_code} "
                f"(URL: {e.request.url})"
            )
            result.errors.append(error_msg)
            logger.error(error_msg)
            # Return stale cached data if available
            stale_games = self._cache.get_games(year, week)
            if stale_games:
                result.games = stale_games
                result.warnings.append(
                    f"Returning stale cached data for week {week} due to HTTP error"
                )
        except ESPNSchemaError as e:
            error_msg = f"Schema error fetching week {week}: {e}"
            result.errors.append(error_msg)
            logger.error(error_msg)
        except httpx.RequestError as e:
            error_msg = (
                f"Failed to fetch week {week} results: network error ({e}) "
                f"(URL: {ESPN_SCOREBOARD_URL})"
            )
            result.errors.append(error_msg)
            logger.error(error_msg)
            # Return stale cached data if available
            stale_games = self._cache.get_games(year, week)
            if stale_games:
                result.games = stale_games
                result.warnings.append(
                    f"Returning stale cached data for week {week} due to network error"
                )

        return result

    def fetch_live_games(self) -> FetchResult:
        """Fetch current scores and game state for all in-progress games.

        Returns:
            FetchResult containing in-progress games. Returns an empty
            games list (without error) if no games are currently in progress.
        """
        result = FetchResult()

        try:
            url = ESPN_SCOREBOARD_URL
            response = self._client.get(url)
            response.raise_for_status()

            data = response.json()
            all_games = parse_espn_scoreboard(data)

            # Filter to only in-progress games
            result.games = [
                g for g in all_games if g.status == GameStatus.IN_PROGRESS
            ]

        except httpx.TimeoutException:
            error_msg = (
                f"Failed to fetch live games: request timed out after "
                f"{self._timeout}s (URL: {ESPN_SCOREBOARD_URL})"
            )
            result.errors.append(error_msg)
            logger.error(error_msg)
        except httpx.HTTPStatusError as e:
            error_msg = (
                f"Failed to fetch live games: HTTP {e.response.status_code} "
                f"(URL: {e.request.url})"
            )
            result.errors.append(error_msg)
            logger.error(error_msg)
        except ESPNSchemaError as e:
            error_msg = f"Schema error fetching live games: {e}"
            result.errors.append(error_msg)
            logger.error(error_msg)
        except httpx.RequestError as e:
            error_msg = (
                f"Failed to fetch live games: network error ({e}) "
                f"(URL: {ESPN_SCOREBOARD_URL})"
            )
            result.errors.append(error_msg)
            logger.error(error_msg)

        return result

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()
