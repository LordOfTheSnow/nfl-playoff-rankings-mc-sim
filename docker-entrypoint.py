"""Docker entrypoint script for the NFL Monte Carlo Playoff Simulator.

Reads the SEASON environment variable, validates it, constructs the CLI
invocation with proper precedence (CLI args override env vars), and execs
into the application process.

The container always listens on port 8080. Use Docker's -p flag to map
any host port to it (e.g. -p 9090:8080).

This script has no third-party dependencies.
"""

from __future__ import annotations

import os
import sys


def resolve_config(env_vars: dict, cmd_args: list[str]) -> list[str]:
    """Resolve the final command-line arguments for the application.

    Reads SEASON from env_vars, validates it, and merges with any CLI
    arguments from cmd_args. CLI args take precedence over env vars.

    Always injects:
      --port 8080
      --static-dir /app/frontend
      --db-path /data/nfl_cache.db

    Args:
        env_vars: Dictionary of environment variables (typically os.environ).
        cmd_args: Additional CLI arguments passed via Docker CMD.

    Returns:
        The final list of command-line arguments for the application.

    Raises:
        SystemExit: If SEASON env var has an invalid value.
    """
    args: list[str] = []

    # --- Validate and resolve SEASON ---
    season_env = env_vars.get("SEASON")
    if season_env is not None and season_env != "":
        try:
            season_int = int(season_env)
            if season_int < 2000 or season_int > 2100:
                raise ValueError()
        except (ValueError, TypeError):
            print(
                f"Error: SEASON environment variable must be an integer "
                f"between 2000 and 2100, got: {season_env}",
                file=sys.stderr,
            )
            sys.exit(1)

    # --- Apply precedence: CLI args override env vars ---

    # Port is always 8080 inside the container
    if "--port" not in cmd_args:
        args.extend(["--port", "8080"])

    # Check if --season is in cmd_args
    has_season_cli = "--season" in cmd_args
    if not has_season_cli:
        if season_env is not None and season_env != "":
            args.extend(["--season", season_env])

    # --- Always inject fixed container paths ---
    # Check if --static-dir is in cmd_args
    if "--static-dir" not in cmd_args:
        args.extend(["--static-dir", "/app/frontend"])

    # Check if --db-path is in cmd_args
    if "--db-path" not in cmd_args:
        args.extend(["--db-path", "/data/nfl_cache.db"])

    # Append any CMD overrides
    args.extend(cmd_args)

    return args


def main() -> None:
    """Entrypoint: validate env, build args, exec into app."""
    # CMD arguments are passed as sys.argv[1:]
    cmd_args = sys.argv[1:]

    # Resolve final arguments
    final_args = resolve_config(dict(os.environ), cmd_args)

    # Build the full command: python -m src <args>
    exec_args = ["python", "-m", "src"] + final_args

    # Replace PID 1 with the application process
    os.execvp("python", exec_args)


if __name__ == "__main__":
    main()
