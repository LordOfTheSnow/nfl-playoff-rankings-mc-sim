"""Cache layer for NFL data with SQLite persistence and TTL policies.

This module provides the Cache class that stores fetched game data locally
with configurable time-to-live policies based on game status.

Note: Full implementation is in task 3.1. This file provides the interface
that DataClient depends on.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.cp_solver import CPSolverResult
    from src.data_client import Game

logger = logging.getLogger(__name__)


class CachePolicy:
    """TTL policies for cached game data based on game status."""

    SCHEDULE_TTL: timedelta = timedelta(hours=24)
    IN_PROGRESS_TTL: timedelta = timedelta(seconds=60)
    COMPLETED_TTL: timedelta | None = None  # Never expires


class Cache:
    """SQLite-based cache for NFL game data with TTL policies.

    Stores game data with UTC timestamps and provides freshness checks
    based on game status-specific TTL policies.
    """

    def __init__(self, db_path: str = "nfl_cache.db") -> None:
        """Initialize the cache with SQLite database.

        Args:
            db_path: Path to the SQLite database file. Use ":memory:" for testing.
        """
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Create database tables and indexes if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                year INTEGER NOT NULL,
                week INTEGER NOT NULL,
                game_date TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                status TEXT NOT NULL,
                home_score INTEGER,
                away_score INTEGER,
                home_points INTEGER,
                away_points INTEGER,
                quarter TEXT,
                clock TEXT,
                fetched_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_games_year_week ON games(year, week);
            CREATE INDEX IF NOT EXISTS idx_games_home_team ON games(home_team);
            CREATE INDEX IF NOT EXISTS idx_games_away_team ON games(away_team);
            CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);

            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                week INTEGER,
                fetched_at TEXT NOT NULL,
                games_count INTEGER NOT NULL,
                success INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS weekly_strengths (
                year INTEGER NOT NULL,
                week INTEGER NOT NULL,
                team TEXT NOT NULL,
                strength REAL NOT NULL,
                PRIMARY KEY (year, week, team)
            );

            CREATE TABLE IF NOT EXISTS cp_solver_cache (
                team TEXT NOT NULL,
                cutoff_week INTEGER NOT NULL,
                season INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                computed_at TEXT NOT NULL,
                PRIMARY KEY (team, cutoff_week, season)
            );
        """)
        self._conn.commit()

    def store_games(self, games: list[Game], year: int) -> None:
        """Store games in the cache with current UTC timestamp.

        Args:
            games: List of Game objects to store.
            year: The season year for these games.
        """
        from src.data_client import Game  # noqa: F811

        now = datetime.now(UTC).isoformat()
        for game in games:
            self._conn.execute(
                """INSERT OR REPLACE INTO games
                   (game_id, year, week, game_date, home_team, away_team, status,
                    home_score, away_score, home_points, away_points, quarter, clock, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    game.game_id,
                    year,
                    game.week,
                    game.date.isoformat(),
                    game.home_team,
                    game.away_team,
                    game.status.value,
                    game.home_score,
                    game.away_score,
                    game.home_points,
                    game.away_points,
                    game.quarter,
                    game.clock,
                    now,
                ),
            )
        self._conn.commit()

        # Log the fetch
        if games:
            weeks = set(g.week for g in games)
            for week in weeks:
                week_games = [g for g in games if g.week == week]
                self._conn.execute(
                    """INSERT INTO fetch_log (year, week, fetched_at, games_count, success)
                       VALUES (?, ?, ?, ?, 1)""",
                    (year, week, now, len(week_games)),
                )
            self._conn.commit()

    def get_games(self, year: int, week: int | None = None) -> list[Game]:
        """Retrieve cached games filtered by year and optional week.

        Args:
            year: The season year.
            week: Optional week number to filter by.

        Returns:
            List of Game objects from the cache.
        """
        from src.data_client import Game, GameStatus
        from datetime import date as date_type

        if week is not None:
            rows = self._conn.execute(
                "SELECT * FROM games WHERE year = ? AND week = ?", (year, week)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM games WHERE year = ?", (year,)
            ).fetchall()

        games = []
        for row in rows:
            games.append(
                Game(
                    game_id=row["game_id"],
                    week=row["week"],
                    date=date_type.fromisoformat(row["game_date"]),
                    home_team=row["home_team"],
                    away_team=row["away_team"],
                    status=GameStatus(row["status"]),
                    home_score=row["home_score"],
                    away_score=row["away_score"],
                    home_points=row["home_points"],
                    away_points=row["away_points"],
                    quarter=int(row["quarter"]) if row["quarter"] is not None else None,
                    clock=row["clock"],
                )
            )
        return games

    def get_team_games(self, year: int, team: str) -> list[Game]:
        """Retrieve all games for a specific team.

        Args:
            year: The season year.
            team: Team name to filter by.

        Returns:
            List of Game objects involving the specified team.
        """
        from src.data_client import Game, GameStatus
        from datetime import date as date_type

        rows = self._conn.execute(
            "SELECT * FROM games WHERE year = ? AND (home_team = ? OR away_team = ?)",
            (year, team, team),
        ).fetchall()

        games = []
        for row in rows:
            games.append(
                Game(
                    game_id=row["game_id"],
                    week=row["week"],
                    date=date_type.fromisoformat(row["game_date"]),
                    home_team=row["home_team"],
                    away_team=row["away_team"],
                    status=GameStatus(row["status"]),
                    home_score=row["home_score"],
                    away_score=row["away_score"],
                    home_points=row["home_points"],
                    away_points=row["away_points"],
                    quarter=int(row["quarter"]) if row["quarter"] is not None else None,
                    clock=row["clock"],
                )
            )
        return games

    def store_weekly_strengths(self, year: int, week: int, strengths: dict[str, float]) -> None:
        """Store pre-computed team strengths for a given cutoff week.

        Args:
            year: Season year.
            week: Cutoff week (strengths computed from games 1..week).
            strengths: Mapping of team name to strength rating.
        """
        for team, strength in strengths.items():
            self._conn.execute(
                """INSERT OR REPLACE INTO weekly_strengths (year, week, team, strength)
                   VALUES (?, ?, ?, ?)""",
                (year, week, team, strength),
            )
        self._conn.commit()

    def get_weekly_strengths(self, year: int) -> dict[int, dict[str, float]]:
        """Retrieve all pre-computed weekly strengths for a season.

        Args:
            year: Season year.

        Returns:
            Mapping of week -> {team -> strength}.
        """
        cursor = self._conn.execute(
            "SELECT week, team, strength FROM weekly_strengths WHERE year = ?",
            (year,),
        )
        result: dict[int, dict[str, float]] = {}
        for row in cursor:
            week = row[0]
            if week not in result:
                result[week] = {}
            result[week][row[1]] = row[2]
        return result

    def is_fresh(self, year: int, week: int) -> bool:
        """Check if cached data for a given year/week is still fresh.

        Freshness is determined by the game status-specific TTL policy:
        - Completed games: always fresh (never expire)
        - In-progress games: fresh if fetched within 60 seconds
        - Scheduled games: fresh if fetched within 24 hours

        Args:
            year: The season year.
            week: The week number.

        Returns:
            True if cached data is fresh, False if stale or missing.
        """
        rows = self._conn.execute(
            "SELECT status, fetched_at FROM games WHERE year = ? AND week = ?",
            (year, week),
        ).fetchall()

        if not rows:
            return False

        now = datetime.now(UTC)
        for row in rows:
            status = row["status"]
            fetched_at = datetime.fromisoformat(row["fetched_at"])
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=UTC)

            age = now - fetched_at

            if status == "completed":
                continue  # Never expires
            elif status == "in-progress":
                if age > CachePolicy.IN_PROGRESS_TTL:
                    return False
            else:
                if age > CachePolicy.SCHEDULE_TTL:
                    return False

        return True

    def get_cache_status(self) -> dict:
        """Return cache status information.

        Returns:
            Dictionary with last_fetch_time and games_cached count.
        """
        row = self._conn.execute(
            "SELECT MAX(fetched_at) as last_fetch FROM games"
        ).fetchone()

        count_row = self._conn.execute("SELECT COUNT(*) as cnt FROM games").fetchone()

        return {
            "last_fetch_time": row["last_fetch"] if row else None,
            "games_cached": count_row["cnt"] if count_row else 0,
        }

    def get_last_fetch_time(self) -> datetime | None:
        """Return the timestamp of the most recent fetch, or None if no data cached."""
        row = self._conn.execute(
            "SELECT MAX(fetched_at) as last_fetch FROM games"
        ).fetchone()
        if row and row["last_fetch"]:
            return datetime.fromisoformat(row["last_fetch"])
        return None

    def store_cp_result(self, team: str, cutoff_week: int, season: int, result: CPSolverResult) -> None:
        """Store a CP solver result in the cache.

        Serializes the CPSolverResult to JSON and stores it keyed by
        (team, cutoff_week, season). Uses INSERT OR REPLACE to handle
        re-storing.

        Args:
            team: Team name.
            cutoff_week: The cutoff week used for the solve.
            season: The season year.
            result: The CPSolverResult to cache.
        """
        from src.cp_solver import ClinchStatus

        result_dict = {
            "team": result.team,
            "status": result.status.value,
            "clinched": result.clinched,
            "eliminated": result.eliminated,
            "exhaustive": result.exhaustive,
            "solve_time_ms": result.solve_time_ms,
            "num_variables": result.num_variables,
            "minimum_seed": result.minimum_seed,
            "magic_number": result.magic_number,
            "error": result.error,
            "record_groups_completed": result.record_groups_completed,
            "record_groups_total": result.record_groups_total,
        }
        result_json = json.dumps(result_dict)
        now = datetime.now(UTC).isoformat()

        self._conn.execute(
            """INSERT OR REPLACE INTO cp_solver_cache
               (team, cutoff_week, season, result_json, computed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (team, cutoff_week, season, result_json, now),
        )
        self._conn.commit()

    def get_cp_result(self, team: str, cutoff_week: int, season: int) -> CPSolverResult | None:
        """Retrieve a cached CP solver result.

        Deserializes the stored JSON back into a CPSolverResult.
        Returns None if no cached result exists for the given key.

        Args:
            team: Team name.
            cutoff_week: The cutoff week used for the solve.
            season: The season year.

        Returns:
            The cached CPSolverResult, or None if not found.
        """
        from src.cp_solver import ClinchStatus, CPSolverResult

        row = self._conn.execute(
            "SELECT result_json FROM cp_solver_cache WHERE team = ? AND cutoff_week = ? AND season = ?",
            (team, cutoff_week, season),
        ).fetchone()

        if row is None:
            return None

        data = json.loads(row["result_json"])
        return CPSolverResult(
            team=data["team"],
            status=ClinchStatus(data["status"]),
            clinched=data["clinched"],
            eliminated=data["eliminated"],
            exhaustive=data["exhaustive"],
            solve_time_ms=data["solve_time_ms"],
            num_variables=data["num_variables"],
            minimum_seed=data["minimum_seed"],
            magic_number=data["magic_number"],
            error=data["error"],
            record_groups_completed=data["record_groups_completed"],
            record_groups_total=data["record_groups_total"],
        )

    def invalidate_cp_cache(self, season: int) -> None:
        """Delete all cached CP solver results for a given season.

        Args:
            season: The season year whose cached results should be removed.
        """
        self._conn.execute(
            "DELETE FROM cp_solver_cache WHERE season = ?",
            (season,),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
