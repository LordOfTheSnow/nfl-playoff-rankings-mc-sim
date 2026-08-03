# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A web app that predicts NFL playoff probabilities via Monte Carlo simulation. Python stdlib HTTP server backend (`src/`), vanilla JS frontend (`frontend/`, no build step). Fetches game data from ESPN's public API, computes strength-of-schedule team ratings, simulates remaining games, applies official NFL tiebreaker rules, and exposes results through a REST API consumed by a hash-routed single-page frontend.

## Context files

Read the following to get the full context of the project:

* @context/doc/api.md
* @context/doc/algorithms.md
* @cpmtext/doc/technical.md

## Commands

### Backend (Python 3.11+)

```bash
source .venv/bin/activate
pip install -e ".[dev]"        # install with pytest/hypothesis

python -m src                  # run server, default port 8080, current season
python -m src --season 2025 --port 8080

pytest tests/ -v                        # run tests (slow tests excluded by default — see pyproject.toml addopts)
pytest tests/test_cp_solver.py -v       # single file
pytest tests/test_cp_solver.py::test_name -v   # single test
pytest tests/ -v -m slow                # include slow tests (opt-in)
```

There is no lint/format command configured in this repo (no ruff/black/mypy config present).

### Frontend (Vitest + fast-check, jsdom)

```bash
npm install
npm test          # vitest run — property-based tests, min 100 iterations each
npm run test:watch
```

Frontend has no build/bundle step — `frontend/` is served as static files directly by the Python server.

### Docker

```bash
docker build -t nfl-playoff-rankings-mc-sim .
docker compose up      # builds, mounts ./:/data, maps port 8080
```

## Architecture

### Backend module responsibilities (`src/`)

- **`server.py`** — `BaseHTTPRequestHandler` subclass (`NFLRequestHandler`) implementing every REST route via long if/elif chains in `do_GET`/`do_POST` (no framework/router). Also serves static frontend files for any non-`/api/` path. `NFLSimulatorServer` (a `ThreadingMixIn` + `HTTPServer`) owns the shared `Cache`, `DataClient`, and current `season_year` for the process lifetime.
- **`data_client.py`** — Fetches game/schedule data from ESPN's public JSON API, defines `Game`/`GameStatus`.
- **`cache.py`** — SQLite persistence with per-status TTL policy (`CachePolicy`): schedule data 24h, in-progress games 60s, completed games never expire. DB path defaults to `nfl_cache.db` (gitignored; also stores solver performance timing rows, rolling window of 50/platform).
- **`team_strength.py`** — Iterative strength-of-schedule rating algorithm with relaxation (50/50 blend to prevent oscillation) and Bayesian dampening toward league average by sample size (see `doc/algorithms.md`).
- **`simulator.py`** — Monte Carlo engine. Each trial simulates all remaining games and calls into `standings.py` for real tiebreaker resolution. Parallelized via `multiprocessing.ProcessPoolExecutor`; uses `fork` context on Unix, falls back to default (`spawn`) on Windows. Workers split iterations into batches with independent RNGs; results (playoff counts, seeding matrices, scenario counters) are merged by summing.
- **`standings.py`** — Full NFL tiebreaker implementation (head-to-head, division/conference record, strength of victory/schedule, net points, etc.) via `compute_standings()` and `determine_playoff_bracket()`. This is the single source of truth for "who makes the playoffs" — both the CP solver and the Monte Carlo simulator validate candidate outcomes through it rather than re-implementing tiebreaker logic.
- **`clinching.py`** — Post-week-14 "clinching scenarios" solver: finds minimal game-outcome condition sets that guarantee/eliminate a playoff spot. Hybrid: full enumeration (3^N) when ≤13 relevant games remain, strength-weighted MC sampling (10k trials/combo) above that. Reduces to strictly-minimal condition sets and dedupes.
- **`cp_solver.py`** — Google OR-Tools CP-SAT solver for mathematically provable clinch/eliminate/alive status, available from week 1 (no week-14 gate). Decomposes by the target team's possible final record (CP-SAT handles win/loss/tie count constraints), then validates each candidate via the real `standings.py` pipeline rather than encoding tiebreakers as constraints — see `doc/algorithms.md` for why this hybrid is fast (3.4×10^30 → tens of ms).
- **`experience_export.py`** — Exports solver performance benchmarks from the SQLite rolling window into `doc/solver-performance.md` (grouped by CPU model/cores/method, median + relative "Factor" column). This file is machine-generated — don't hand-edit it; update `_FILE_HEADER` in this module instead.
- **`nfl_teams.py`** — Static team/conference/division reference data.

### Data flow

`Simulator` and `StandingsEngine`-style computations are instantiated on-demand per API request; `cutoff_week` flows from the HTTP request through `Simulator` → `TeamStrengthCalculator`. Only `Cache` and `DataClient` (and the current season) are long-lived, owned by `NFLSimulatorServer`.

### Frontend (`frontend/js/`, no framework, no build step)

Hash-based SPA routing implemented in `app.js`:

- `#standings` (default), `#team/<name>`, `#schedule-grid`, `#simulate`, `#results`

`app.js` owns routing, global error/loading notifications, and nav state. Other files are per-view: `standings.js`, `schedule.js`, `schedule-grid.js`, `simulation.js`, `statistics.js`, `charts.js`. `api.js` is the fetch wrapper for all `/api/*` calls. Bootstrap 5.3.8 is loaded via CDN (no local copy/bundling).

### Season selection

The active season is server-side state (`NFLSimulatorServer.season_year`), changed via `POST /api/set-season`, not a per-request parameter — the frontend season selector switches this globally without restarting the server.

## Conventions specific to this repo

- **Docs must stay in sync with code.** Per `.kiro/steering/docs-sync.md`: any change to API endpoints, request/response shapes, or algorithm behavior in `src/` or `frontend/` must be reflected in `doc/api.md`, `README.md` (if user-facing), and/or `doc/algorithms.md` / `doc/technical.md` as appropriate. Do not hand-edit `doc/solver-performance.md` — it's generated.
- **Release process** (`.kiro/steering/release-process.md`, only when explicitly asked to prepare a release): bump `version` in both `pyproject.toml` and `uv.lock`, update the `**v0.x.y**` string in `README.md`, move `## [Unreleased]` CHANGELOG items into a new dated section, update compare-link references at the bottom of `CHANGELOG.md`, remove completed items from the README `## ToDo` section. The release workflow triggers automatically on merge to `main` when the version changes; PR title becomes the GitHub Release name and the CHANGELOG section becomes the release body. Don't bump version for hotfixes that shouldn't cut a release.
- **`.kiro/specs/`** contains historical feature specs (requirements/design/tasks) for past work — useful background when touching an area like the CP solver, schedule grid, or experience export, but not necessarily reflective of current code state.
- Tests use `pytest.mark.slow` for expensive tests (e.g. real parallel-simulation runs); these are excluded by default via `addopts` in `pyproject.toml` and must be opted into with `-m slow`.
- Property-based tests (both Python/Hypothesis in `tests/strategies/` and JS/fast-check in `frontend/tests/`) are used for tiebreaker/standings/schedule-grid logic given the combinatorial nature of NFL rules — prefer extending strategies over hand-written fixtures when adding coverage in these areas.
