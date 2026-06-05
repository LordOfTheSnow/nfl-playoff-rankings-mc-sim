# Implementation Plan: Monte Carlo NFL Playoff Simulator

## Overview

This plan implements a Python web application that predicts NFL playoff outcomes using Monte Carlo simulation. The system fetches real NFL game data from ESPN's public JSON API, computes strength-of-schedule-weighted team ratings via iterative convergence, simulates remaining games, applies official NFL tiebreaker rules, and presents probability distributions through an interactive browser-based UI. Implementation follows a layered approach: data models and interfaces first, then computation engines, then the web server and frontend.

## Tasks

- [x] 1. Set up project structure, data models, and test infrastructure
  - [x] 1.1 Create project directory structure and configuration files
    - Create `pyproject.toml` with Python 3.11+ requirement, pytest, hypothesis, and httpx as dev dependencies
    - Create directory structure: `src/`, `tests/`, `tests/strategies/`, `frontend/`, `frontend/css/`, `frontend/js/`
    - Create `src/__init__.py`, `tests/__init__.py`, `tests/strategies/__init__.py`
    - Create `src/nfl_teams.py` with the `NFL_TEAMS` dictionary mapping conferences → divisions → team lists (32 teams total)
    - _Requirements: 10.1_

  - [x] 1.2 Define core data models in `src/data_client.py`
    - Create `GameStatus` enum with values: SCHEDULED, IN_PROGRESS, COMPLETED, POSTPONED, CANCELLED
    - Create frozen `Game` dataclass with fields: game_id, week, date, home_team, away_team, status, home_score, away_score, home_points, away_points, quarter, clock
    - Create `FetchResult` dataclass with fields: games, warnings, errors
    - Define `DataClient` class skeleton with `__init__`, `fetch_season_schedule`, `fetch_week_results`, `fetch_live_games` method signatures
    - _Requirements: 1.2, 2.2, 3.2_

  - [x] 1.3 Create Hypothesis test strategies in `tests/strategies/`
    - Create `tests/strategies/games.py` with strategies for generating valid `Game` objects with all statuses
    - Create `tests/strategies/espn_json.py` with strategies for generating valid ESPN scoreboard JSON responses
    - Create `tests/strategies/standings.py` with strategies for generating W-L-T records and team strength ratings
    - Create `tests/conftest.py` with shared fixtures (e.g., sample games, ALL_TEAMS list)
    - _Requirements: 1.2, 2.2, 5.3, 9.4, 10.2_

  - [ ]* 1.4 Write property test skeletons for data parsing (Properties 1-3)
    - Create `tests/test_data_client.py` with test function signatures for:
      - **Property 1: ESPN JSON Parsing Round-Trip** — parsing valid ESPN JSON produces correct Game objects
      - **Property 2: Schema Error Detection** — missing required fields raise schema errors identifying the field
      - **Property 3: Game Status Filtering** — filtering for completed games returns only completed games
    - _Requirements: 1.2, 1.4, 2.3_

  - [ ]* 1.5 Write property test skeletons for cache behavior (Properties 4-5)
    - Create `tests/test_cache.py` with test function signatures for:
      - **Property 4: Cache Storage Round-Trip** — storing and retrieving games produces identical objects with timestamps
      - **Property 5: Cache TTL Freshness by Game Status** — freshness checks respect TTL policies per status
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 1.6 Write property test skeletons for simulation invariants (Properties 6-10)
    - Create `tests/test_simulator.py` with test function signatures for:
      - **Property 6: Simulation Probability Invariants** — probability sums and ranges are correct
      - **Property 7: Completed Games Immutability** — fixed inputs don't change between trials
      - **Property 8: Trial Count Validation** — accepts [100, 1M], rejects outside range
      - **Property 9: Game Outcome Probability Proportional to Strength** — win ratios approximate strength ratios
    - Create `tests/test_cutoff_week.py` with test function signatures for:
      - **Property 10: Cutoff Week Validation** — accepts [1, 18], rejects outside range
    - _Requirements: 5.3, 5.4, 5.5, 5.6, 5.7, 5.9, 5.12, 9.6, 9.7_

  - [ ]* 1.7 Write property test skeletons for cutoff week, team strength, and standings (Properties 11-22)
    - Add to `tests/test_cutoff_week.py`:
      - **Property 11: Cutoff Week Game Partitioning** — correct game classification by cutoff
      - **Property 12: Default Cutoff Week Determination** — auto-detects latest fully completed week
    - Create `tests/test_team_strength.py` with test function signatures for:
      - **Property 15: Team Strength Convergence** — terminates with convergence or max iterations
      - **Property 16: Team Strength Monotonicity** — stronger wins increase rating
      - **Property 17: Team Strength Input Filtering** — only uses completed games up to cutoff
    - Create `tests/test_standings.py` with test function signatures for:
      - **Property 18: Win Percentage Formula** — (W + 0.5×T) / (W+L+T)
      - **Property 19: Playoff Bracket Structure** — 7 teams per conference, 4 div champs + 3 WC
      - **Property 20: Tiebreaker Total Ordering** — produces strict ordering
      - **Property 21: Point-Based Tiebreaker Step Handling** — skips point steps for simulated games
      - **Property 22: Standings Sort Order** — sorted by win% descending, alphabetical for ties
    - Add to `tests/test_simulator.py`:
      - **Property 13: Distinct Scenarios Uniqueness** — no duplicate scenarios
      - **Property 14: Impact Games Ordering** — sorted by impact, max 5 entries
    - _Requirements: 5.8, 5.10, 5.11, 5.13, 6.1, 6.4, 9.2, 9.3, 9.4, 9.5, 9.9, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.13, 10.14, 12.3, 12.4_

- [x] 2. Checkpoint - Verify project structure and test skeletons
  - Ensure all test files are importable and pytest discovers them (tests will fail since implementation is pending), ask the user if questions arise.

- [x] 3. Implement Cache Layer and Data Client
  - [x] 3.1 Implement SQLite cache layer in `src/cache.py`
    - Create `CachePolicy` class with TTL constants: SCHEDULE_TTL (24h), IN_PROGRESS_TTL (60s), COMPLETED_TTL (None/never)
    - Create `Cache` class with SQLite database initialization (create tables and indexes on init)
    - Implement `store_games()` — upsert games with UTC `fetched_at` timestamp
    - Implement `get_games(year, week)` — retrieve games filtered by year and optional week
    - Implement `get_team_games(year, team)` — retrieve all games for a specific team
    - Implement `is_fresh(year, week)` — check TTL freshness based on game status and fetched_at
    - Implement `get_cache_status()` — return last fetch time and game count
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [ ]* 3.2 Write property tests for cache (Properties 4-5)
    - **Property 4: Cache Storage Round-Trip**
    - **Validates: Requirements 4.1, 4.6**
    - **Property 5: Cache TTL Freshness by Game Status**
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5**

  - [x] 3.3 Implement ESPN JSON parser and Data Client in `src/data_client.py`
    - Implement ESPN JSON response parsing: extract game_id, date, home_team, away_team, status, scores, points, quarter, clock from nested JSON structure
    - Implement status mapping: STATUS_SCHEDULED→scheduled, STATUS_IN_PROGRESS→in-progress, STATUS_FINAL→completed, STATUS_POSTPONED→postponed, STATUS_CANCELED→cancelled
    - Implement schema error detection: raise descriptive errors when required fields are missing
    - Implement `fetch_season_schedule(year)` — fetch weeks 1-18 with 30s timeout, handle partial failures with warnings
    - Implement `fetch_week_results(year, week)` — fetch specific week results
    - Implement `fetch_live_games()` — fetch current in-progress games
    - Integrate with Cache: check freshness before fetching, store results after fetch, return stale data on network failure
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 4.7, 4.8_

  - [ ]* 3.4 Write property tests for data client parsing (Properties 1-3)
    - **Property 1: ESPN JSON Parsing Round-Trip**
    - **Validates: Requirements 1.2, 2.2, 2.5, 3.2**
    - **Property 2: Schema Error Detection**
    - **Validates: Requirements 1.4**
    - **Property 3: Game Status Filtering**
    - **Validates: Requirements 2.3**

  - [ ]* 3.5 Write unit tests for data client error handling
    - Test ESPN API unreachable (timeout after 30s) returns error with URL and status code
    - Test ESPN API HTTP error returns appropriate error indication
    - Test partial week failures return successful games + warning count
    - Test schema change detection identifies missing field name
    - Test no in-progress games returns empty result without error
    - Test cache refresh failure returns stale data with outdated indicator
    - _Requirements: 1.3, 1.4, 1.5, 2.4, 3.3, 3.4, 4.8_

- [x] 4. Implement Team Strength Calculator
  - [x] 4.1 Implement iterative team strength algorithm in `src/team_strength.py`
    - Create `TeamRating` dataclass with team, strength, games_played fields
    - Create `TeamStrengthCalculator` class with CONVERGENCE_THRESHOLD=0.001 and MAX_ITERATIONS=100
    - Implement `calculate(completed_games)` — returns dict[str, float] mapping team→strength
    - Implement `_initial_ratings(teams)` — initialize all teams at 1.0
    - Implement `_iterate(ratings, games)` — compute new ratings with win weight=opponent rating, loss weight=1/opponent rating, tie weight=0.5×opponent rating
    - Implement normalization so average rating is 1.0
    - Implement convergence check: stop when max delta < 0.001
    - Handle max iterations (100) with warning log
    - Assign league-average strength (1.0) to teams with no completed games
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.8, 9.9_

  - [ ]* 4.2 Write property tests for team strength (Properties 15-17)
    - **Property 15: Team Strength Convergence**
    - **Validates: Requirements 9.4, 9.5**
    - **Property 16: Team Strength Monotonicity**
    - **Validates: Requirements 9.2, 9.3**
    - **Property 17: Team Strength Input Filtering**
    - **Validates: Requirements 9.9, 5.13**

  - [ ]* 4.3 Write unit tests for team strength edge cases
    - Test two teams with equal records get equal strength
    - Test team with no games gets average strength (1.0)
    - Test convergence is achieved within 100 iterations for typical game sets
    - Test non-convergence warning is logged after 100 iterations
    - _Requirements: 9.4, 9.5, 9.7, 9.8_

- [x] 5. Implement Standings Engine
  - [x] 5.1 Implement NFL standings computation in `src/standings.py`
    - Create `Conference`, `Division` enums
    - Create `TeamStanding` dataclass with all fields (team, conference, division, W-L-T, win_percentage, division_record, conference_record, points_for/against, seed, is_division_champion, is_playoff_team, games_behind)
    - Create `PlayoffBracket` dataclass with afc_seeds and nfc_seeds
    - Implement `compute_standings(games, simulated_outcomes)` — calculate W-L-T records from game results and optional simulated outcomes
    - Implement win_percentage calculation: (W + 0.5×T) / (W+L+T)
    - Implement games_behind calculation: ((leader_W - team_W) + (team_L - leader_L)) / 2
    - Implement division record and conference record tracking
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 5.2 Implement tiebreaker procedures in `src/standings.py`
    - Implement division tiebreaker steps in order: head-to-head, division record, common games, conference record, strength of victory, strength of schedule, point-based steps (skip for simulated), coin toss
    - Implement conference tiebreaker steps in order: head-to-head (if applicable), conference record, common games (min 4), strength of victory, strength of schedule, point-based steps (skip for simulated), coin toss
    - Implement multi-team tie handling: apply collectively, restart from step 1 when one team eliminated
    - Implement point-based step skipping for simulated games (no point data available)
    - Implement point-based steps using actual data for completed games
    - _Requirements: 10.4, 10.5, 10.6, 10.13, 10.14_

  - [x] 5.3 Implement playoff bracket construction in `src/standings.py`
    - Implement `determine_playoff_bracket(standings)` — select 7 teams per conference
    - Select 4 division champions (best record per division), seed 1-4 by overall record with conference tiebreakers
    - Select 3 wild card teams (best remaining conference records), seed 5-7
    - Construct Wild Card Round pairings: 2v7, 3v6, 4v5 (higher seed hosts)
    - Grant #1 seed first-round bye
    - _Requirements: 10.3, 10.7, 10.8, 10.9_

  - [ ]* 5.4 Write property tests for standings (Properties 18-22)
    - **Property 18: Win Percentage Formula**
    - **Validates: Requirements 10.2**
    - **Property 19: Playoff Bracket Structure**
    - **Validates: Requirements 10.3, 10.7**
    - **Property 20: Tiebreaker Total Ordering**
    - **Validates: Requirements 10.4, 10.5, 10.6**
    - **Property 21: Point-Based Tiebreaker Step Handling**
    - **Validates: Requirements 10.13, 10.14**
    - **Property 22: Standings Sort Order**
    - **Validates: Requirements 12.3, 12.4**

  - [ ]* 5.5 Write unit tests for standings and bracket construction
    - Test 7 teams per conference qualify for playoffs
    - Test division champion seeding (1-4) by win percentage
    - Test wild card seeding (5-7) by conference record
    - Test bracket pairings: 2v7, 3v6, 4v5
    - Test #1 seed gets bye
    - Test games_behind calculation
    - _Requirements: 10.3, 10.7, 10.8, 10.9_

- [x] 6. Checkpoint - Verify computation layer
  - Ensure all tests pass for cache, data client, team strength, and standings modules, ask the user if questions arise.

- [x] 7. Implement Monte Carlo Simulator
  - [x] 7.1 Implement simulation engine in `src/simulator.py`
    - Create `SimulationConfig` dataclass with iterations (default 10000), tie_probability (default 0.005), cutoff_week (optional), min/max iterations
    - Create `TeamResult`, `ScenarioResult`, `SimulationResult` dataclasses
    - Implement `Simulator` class with `run(all_games)` method
    - Implement `_determine_cutoff_week(games)` — find latest week where ALL games are completed
    - Implement game partitioning: fixed inputs (completed games in weeks 1..cutoff) vs simulated (all others)
    - Implement `_simulate_game(home, away, strengths, tie_prob)` — tie probability first, then split remaining by strength ratio
    - Implement trial loop: simulate remaining games, compute standings via StandingsEngine, record playoff outcomes
    - Implement probability aggregation: playoff probability, seed distribution per team
    - Implement scenario tracking: identify distinct playoff brackets, report top 50 by frequency
    - Implement impact game computation: identify top 5 games with largest effect on a team's playoff probability
    - Implement input validation: reject iterations outside [100, 1M], cutoff_week outside [1, 18]
    - Implement low_confidence flag when iterations < 100
    - Integrate with TeamStrengthCalculator (using only fixed input games)
    - Treat in-progress games as unplayed (simulate from scratch)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 7.2 Write property tests for simulation (Properties 6-9, 13-14)
    - **Property 6: Simulation Probability Invariants**
    - **Validates: Requirements 5.3, 6.2, 6.3**
    - **Property 7: Completed Games Immutability**
    - **Validates: Requirements 5.4**
    - **Property 8: Trial Count Validation**
    - **Validates: Requirements 5.5, 5.6**
    - **Property 9: Game Outcome Probability Proportional to Strength**
    - **Validates: Requirements 5.7, 9.6, 9.7**
    - **Property 13: Distinct Scenarios Uniqueness**
    - **Validates: Requirements 6.1**
    - **Property 14: Impact Games Ordering**
    - **Validates: Requirements 6.4**

  - [ ]* 7.3 Write property tests for cutoff week logic (Properties 10-12)
    - **Property 10: Cutoff Week Validation**
    - **Validates: Requirements 5.9, 5.12**
    - **Property 11: Cutoff Week Game Partitioning**
    - **Validates: Requirements 5.8, 5.10, 5.13**
    - **Property 12: Default Cutoff Week Determination**
    - **Validates: Requirements 5.11**

  - [ ]* 7.4 Write unit tests for simulator edge cases
    - Test in-progress games treated as unplayed (live scores ignored)
    - Test tie probability configuration with non-default values
    - Test low confidence flag when < 100 iterations
    - Test top 50 scenario limit (not unlimited)
    - Test default cutoff week auto-detection
    - Test invalid iteration count rejection (< 100, > 1M, non-integer)
    - Test invalid cutoff_week rejection (< 1, > 18, non-integer)
    - _Requirements: 5.5, 5.6, 5.7, 5.8, 5.11, 5.12, 6.5_

- [x] 8. Checkpoint - Verify simulation engine
  - Ensure all tests pass for the simulator module including property tests and unit tests, ask the user if questions arise.

- [x] 9. Implement Web Server and REST API
  - [x] 9.1 Implement HTTP server and REST API in `src/server.py`
    - Create `NFLSimulatorServer` class using Python's `http.server` module
    - Implement CLI argument parsing: `--port` (default 8080), `--season` (year), `--static-dir` (default "frontend")
    - Print local URL on startup (e.g., "http://localhost:8080")
    - Implement static file serving for frontend directory (HTML, CSS, JS)
    - Implement `GET /api/status` — return cache status (last_fetch_time, games_cached, season_year)
    - Implement `POST /api/fetch-data` — trigger ESPN data fetch via DataClient, return games_fetched count and warnings
    - Implement `POST /api/simulate` — accept JSON body with optional iterations (default 10000) and cutoff_week, run simulation, return full results
    - Implement `GET /api/standings` — compute and return current standings from cached data
    - Implement `GET /api/team/<name>` — return team schedule (all games for that team)
    - Implement consistent JSON error response format: {error, message, code, details}
    - Return HTTP 409 when simulation called without cached data
    - Return HTTP 5xx on ESPN API failures
    - Return HTTP 400 on invalid request parameters
    - Display usage help and exit with non-zero code on invalid CLI arguments
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12_

  - [ ]* 9.2 Write unit tests for server API endpoints
    - Test GET /api/status returns cache status JSON
    - Test POST /api/fetch-data triggers fetch and returns count
    - Test POST /api/simulate with valid params returns results
    - Test POST /api/simulate with invalid iterations returns 400
    - Test POST /api/simulate without cached data returns 409
    - Test GET /api/standings returns standings JSON
    - Test GET /api/team/<name> returns team schedule JSON
    - Test invalid CLI arguments show usage and exit non-zero
    - Test error response format consistency
    - _Requirements: 8.3, 8.4, 8.5, 8.7, 8.8, 8.9, 8.11, 8.12_

- [x] 10. Implement Frontend
  - [x] 10.1 Create HTML shell and CSS styles
    - Create `frontend/index.html` with navigation shell (standings, simulate, results links), content container, and script includes
    - Create `frontend/css/styles.css` with responsive layout (1024px-1920px), division/conference grouping styles, table styles, progress indicator, error notification area, and visual distinction for division leaders
    - _Requirements: 7.1, 11.5, 11.6, 11.8_

  - [x] 10.2 Implement JavaScript application core and API client
    - Create `frontend/js/app.js` with hash-based SPA routing (#standings, #team/<name>, #simulate, #results), navigation handling, and view switching
    - Create `frontend/js/api.js` with REST API client functions: fetchStatus(), fetchData(), runSimulation(iterations, cutoffWeek), getStandings(), getTeamSchedule(name)
    - Implement error handling: display JSON error messages in notification area without page reload
    - _Requirements: 11.3, 11.4, 11.6_

  - [x] 10.3 Implement Standings View
    - Create `frontend/js/standings.js` with standings rendering logic
    - Display standings grouped by conference (AFC/NFC) and division (East, North, South, West)
    - Show columns: team name, W, L, T, Win%, Games Behind
    - Sort by Win% descending within division; alphabetical for ties
    - Bold/highlight division leaders
    - Implement conference filter (AFC/NFC/All)
    - Make team names clickable → navigate to #team/<name>
    - _Requirements: 7.8, 11.7, 11.9, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [x] 10.4 Implement Team Schedule View
    - Create `frontend/js/schedule.js` with team schedule rendering logic
    - Display header with team name, W-L-T record, Win%
    - List all 18 weeks chronologically
    - Show completed games: week, opponent, home/away, score, W/L/T result
    - Show in-progress games: opponent, home/away, current score, quarter, clock
    - Show scheduled games: week, opponent, home/away, date
    - Visual distinction between game statuses (color/icon)
    - Back navigation to standings
    - Display "no schedule data available" message when no games exist
    - _Requirements: 7.9, 11.10, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8_

  - [x] 10.5 Implement Simulation Controls and Results Views
    - Create `frontend/js/simulation.js` with simulation controls and results rendering
    - Simulation controls: numeric input for iterations (100-1,000,000, default 10,000), week selector (dropdown/slider) for cutoff_week (1-18) with default = latest completed week, "Run Simulation" button, "Fetch Data" button
    - Display label showing selected cutoff week ("Games after week N will be simulated")
    - Progress indicator while simulation runs
    - Results: summary table with playoff probabilities by conference (sorted descending, alphabetical for ties)
    - Results: seeding probability matrix (teams × seeds 1-7) grouped by conference
    - Results: top 50 most likely distinct playoff bracket scenarios with probabilities
    - Click team → show scenario details with top 5 impact games
    - Display team strength ratings alongside probabilities
    - _Requirements: 5.5, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 9.10, 11.1, 11.2, 11.7, 11.11, 11.12, 11.13, 11.14_

  - [x] 10.6 Implement chart rendering
    - Create `frontend/js/charts.js` with bar chart/heatmap rendering for seeding probability distribution
    - Render visual chart showing seeding probability distribution for each team within a selected conference
    - Use canvas or SVG (no external dependencies)
    - _Requirements: 7.6_

- [x] 11. Checkpoint - Verify full application
  - Ensure all tests pass (pytest tests/ -v), verify the server starts and serves the frontend, ask the user if questions arise.

- [x] 12. Integration wiring and final tests
  - [x] 12.1 Wire all components together and create application entry point
    - Create `src/__main__.py` (or `main.py`) as the application entry point that instantiates Cache, DataClient, TeamStrengthCalculator, Simulator, StandingsEngine, and NFLSimulatorServer
    - Ensure all components are properly connected: server uses data client for fetching, simulator uses team strength calculator and standings engine
    - Verify cutoff_week parameter flows through API → Simulator → TeamStrengthCalculator
    - _Requirements: 8.1, 8.2_

  - [ ]* 12.2 Write integration tests for component interactions
    - Test Data Client → Cache → (mocked) ESPN API flow
    - Test REST API → Simulator → Standings Engine pipeline
    - Test full simulation run with known game data producing expected bracket
    - Test cutoff_week parameter flowing through API → Simulator → Team Strength
    - Test cache staleness triggering re-fetch
    - Test standings API returning computed standings from cached data
    - Test team schedule API returning all games for a specific team
    - Test points data flowing from Data Client through to Standings Engine tiebreakers
    - _Requirements: 1.1, 4.7, 5.1, 5.13, 8.3, 8.4, 8.11, 8.12_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (18 properties total)
- Unit tests validate specific examples and edge cases
- The design specifies Python 3.11+ with type hints on all public functions
- SQLite database (`nfl_cache.db`) is used for caching — no external database setup required
- Frontend is plain HTML/CSS/JS with no build step — served directly by the Python HTTP server
- ESPN API requires no authentication — uses public undocumented endpoints
- In-progress games are treated as unplayed in simulation (live scores are informational only)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "1.5", "1.6", "1.7"] },
    { "id": 2, "tasks": ["3.1", "3.3"] },
    { "id": 3, "tasks": ["3.2", "3.4", "3.5"] },
    { "id": 4, "tasks": ["4.1", "5.1"] },
    { "id": 5, "tasks": ["4.2", "4.3", "5.2", "5.3"] },
    { "id": 6, "tasks": ["5.4", "5.5"] },
    { "id": 7, "tasks": ["7.1"] },
    { "id": 8, "tasks": ["7.2", "7.3", "7.4"] },
    { "id": 9, "tasks": ["9.1"] },
    { "id": 10, "tasks": ["9.2", "10.1", "10.2"] },
    { "id": 11, "tasks": ["10.3", "10.4", "10.5", "10.6"] },
    { "id": 12, "tasks": ["12.1"] },
    { "id": 13, "tasks": ["12.2"] }
  ]
}
```
