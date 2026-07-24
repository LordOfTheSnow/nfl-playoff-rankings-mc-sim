# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.1] - 2026-07-24

### Added
- Adaptive solver timing: `get_ms_per_eval()` uses historical timing data from cache instead of on-demand benchmarking
- SQLite `solver_timing` table stores per-run timing measurements (rolling window of 50 records)
- `GET /api/solver-timings` endpoint returning timing history with count and average ms/eval
- "Timing History" button and modal in the clinching section showing collected calibration data
- `ClinchingResult.total_evals` field exposing actual evaluation count for external timing computation
- Server stores timing after each successful clinching scenarios response delivery

### Changed
- Clinch estimate endpoint no longer runs explicit `run_benchmark()` — uses adaptive cache-based timing
- Time estimate range multipliers adjusted from 2×–20× to 8×–15× for more realistic predictions
- `estimate_clinching()` accepts optional `cache` parameter for adaptive timing

### Fixed
- Time estimate lower bound was unrealistically optimistic (2× multiplier didn't account for minimality testing overhead)
- Timing modal table used monospace `.numeric` class causing inconsistent font sizes — replaced with plain right-alignment

## [0.7.0] - 2026-07-23

### Added
- CP solver architecture rework: pure constraint-based (no callbacks, no enumeration)
  - Three-tier solver: arithmetic fast-paths → division clinch → CP-SAT constraint model
  - Division-aware elimination: models division winners with H2H tiebreaker constraints
  - Wild card modeled correctly: counts only non-division-winners as competitors
  - Zero remaining games shortcut: uses standings engine directly
  - 0.3s for all 32 teams (was 30-60s+ before)
- Clinching scenarios: user-configurable enumeration threshold slider (5-14 games)
- Clinching scenarios: user-configurable sampling iterations (100-100,000)
- Clinching scenarios: cancel button to abort long-running computations
- Clinching scenarios: time estimate shown as range (accounts for variable post-processing)
- Clinching scenarios: uses same CPU core count as main MC simulation
- Server-side benchmark: measures actual ms/eval on first clinch-estimate request (cached 24h)
- CP solver badges auto-run on standings page load (no manual button needed)
- OR-Tools is now a standard dependency (was optional `[cp]` extra)
- Favicon: Monte Carlo die (SVG)
- Docker: compose.yaml uses directory bind mount (`./data:/data`)

### Fixed
- Critical: `determine_playoff_bracket` did not derive `simulated_game_ids` from `simulated_outcomes` — tiebreaker used actual scores instead of simulated outcomes in MC simulation
- CP solver: false "clinched" when no division rivals in contenders list
- CP solver: false "eliminated" for division winners with fewer wins than 7th-place team
- CP solver: crash on season with no completed games
- Docker: `PlayoffValidator` class crash when OR-Tools not installed
- Clinching scenarios: enumeration threshold configurable (default lowered from 13 to 9)

### Changed
- Clinching scenarios log output shows iterations (sampling) or threshold (enumeration)
- Frontend standings page: CP solver runs automatically, cached results load instantly
- Server: ThreadingMixIn for concurrent requests
- SQLite: `check_same_thread=False` for thread safety

## [0.6.2] - 2026-07-21

### Fixed
- Critical: `determine_playoff_bracket` did not derive `simulated_game_ids` from `simulated_outcomes` — tiebreaker functions used actual game scores instead of simulated outcomes, causing incorrect division winner determination in both MC simulation and CP solver
- MC simulation incorrectly showed 0% playoff probability for teams that could win their division via tiebreaker in simulated scenarios (e.g., Ravens at cutoff week 16)

## [0.6.1] - 2026-07-21

### Changed
- OR-Tools is now a standard dependency (was optional `[cp]` extra)
- `pip install -e .` includes everything needed — no extras required
- Dockerfile uses plain `pip install .` (no `.[cp]` needed)

### Fixed
- CP solver: false "clinched" for all teams when no division rivals in contenders list
- CP solver: false "eliminated" for division winners with fewer wins than 7th-place team (Tier 1b now division-aware)
- CP solver: crash on season with no completed games (returns "alive" for all teams)
- Docker: `PlayoffValidator` class crash when OR-Tools not installed (`cp_model` undefined at module level)
- Docker: compose.yaml uses directory bind mount (`./data:/data`) instead of file mount

## [0.6.0] - 2026-07-21

### Added
- CP-SAT constraint solver for mathematical clinching/elimination detection (Google OR-Tools)
- Pure constraint-based architecture: no callbacks, no enumeration — single Solve() per check
- Three-tier solver: arithmetic fast-paths → division clinch → CP-SAT constraint model
- Division-aware elimination: models division winners explicitly, won't falsely eliminate division winners
- H2H-aware division constraints: accounts for decided head-to-head records in division winner determination
- Wild card modeled correctly: counts only non-division-winners as competitors for 3 spots
- Zero remaining games shortcut: uses standings engine directly (no model needed)
- REST API endpoints: `GET /api/cp-clinch/{team}` and `GET /api/cp-clinch-all`
- Per-team caching in bulk endpoint (instant on repeat visits)
- Frontend clinch/elimination badges on standings view (x=clinched, e=eliminated)
- Hover tooltip on badges showing solve time, remaining games, scenarios checked
- Auto-run on page load with "Computing clinch/elimination…" spinner hint
- SQLite cache for CP solver results with automatic invalidation on data fetch
- Standings page respects cutoff week selector (shows records only through that week)
- OR-Tools as optional dependency (`pip install -e ".[cp]"`)
- Favicon: Monte Carlo die (SVG)
- Legend section on standings page explaining badges and tooltip values
- Server uses ThreadingMixIn for concurrent request handling (CP solver runs in background)

### Fixed
- Playoff bracket tiebreaker resolution now uses full NFL tiebreaker procedure (H2H, division record, conference record, SoV, SoS, net points) instead of alphabetical fallback
- Tiebreaker functions correctly handle simulated game outcomes via module-level `_simulated_winners`
- SQLite `check_same_thread=False` for thread-safe access with ThreadingMixIn
- BrokenPipeError silently handled when client disconnects during CP solver computation

### Performance
- 0.3s for all 32 teams at any cutoff week (sequential, single core)
- Instant for cached results
- No timeouts or inconclusive results under normal conditions

## [0.5.0] - 2026-07-17

### Added

- Clinching scenarios solver (`src/clinching.py`): finds all minimal game-outcome combinations that guarantee a team a playoff spot
  - Hybrid approach: full enumeration (3 outcomes per game) when ≤ 13 relevant games, strength-weighted Monte Carlo sampling (10,000 trials) otherwise
  - Groups results by the team's own remaining record (e.g., 3-1, 2-2, 1-3)
  - Strict minimality: every condition in a scenario is necessary — removing any one breaks the guarantee
  - Parallelized across CPU cores using the existing multiprocessing pattern
  - Hard gate: only available after week 14 (game space too large earlier)
- Preflight estimate endpoint `GET /api/clinch-estimate?team=<name>&cutoff_week=<n>` returns method, relevant game count, and estimated runtime before the user commits to the computation
- Backend endpoint `POST /api/clinching-scenarios` replaces both old path analysis endpoints
- UI: "Clinching Scenarios" button on the simulation results page for teams with 0% < playoff probability < 100%
- UI: spinning status indicator with elapsed timer and descriptive phase messages during computation
- UI: results rendered as collapsible record groups sorted by fewest conditions first

### Changed

- Replaced the old Playoff Path Analysis (Monte Carlo causality-filtered) and Guaranteed Path Solver (combinatorial iterative deepening) with the unified Clinching Scenarios Solver
- Removed `POST /api/analyze-path` and `POST /api/guaranteed-path` endpoints
- Removed `src/elimination.py` module (old guaranteed path solver)
- Removed `Simulator.analyze_path()` method from `src/simulator.py`
- Updated README screenshot and documentation to reflect the new feature
- "Top N Most Likely Playoff Scenarios" section is now collapsible (collapsed by default)
- Disclaimer text moved into the navbar header below the title
- Team logo displayed next to team name in the detail panel heading
- Added spacing between the scenarios section and the team detail panel

### Fixed

- Clinching solver used game status to determine remaining games — failed on completed seasons with a retroactive cutoff week. Now uses week number purely.
- `compute_standings` received only fixed games, causing simulated outcome game_ids to silently fail lookup. Now passes all games so the lookup works correctly.
- False "Clinches regardless" displayed when the minimality check found no single necessary condition (but multi-game flips could still eliminate the team). Now only shown when ALL game-level combinations for a record truly clinch.
- Redundant dominated scenarios shown (e.g., a 3-condition scenario that is a superset of a 1-condition scenario). Post-processing now removes scenarios whose conditions are a strict superset of a simpler scenario.
- False "No path to playoffs" for some records due to testing only one game-level combination per W-L-T record. Now tests all combinations (tiebreakers depend on which specific games are won/lost).
- Sampling used uniform random outcomes, making qualifying universes nearly impossible to find for teams with moderate playoff probability. Now uses strength-weighted sampling (same algorithm as the main simulator).
- Performance: reduced from 100K to 10K MC samples, capped minimality reduction at 200 universes, and deduplicated team records — bringing runtime from hours to ~2 minutes.

## [0.4.0] - 2026-07-14

### Added

- Docker containerization: multi-stage `Dockerfile` (python:3.14-slim builder + runtime), `compose.yaml`, and `docker-entrypoint.py` for running the app in a container
- Named volume support for persistent SQLite database across container restarts
- Season selector dropdown in the navbar allowing runtime season switching without restarting the server
- Backend API endpoint `POST /api/set-season` for changing the active season year at runtime
- Dependabot configuration for automated pip and Docker base image update PRs (`.github/dependabot.yml`)

### Changed

- Container always listens on fixed port 8080 internally; host port mapping via Docker `-p` flag only
- `SEASON` environment variable remains supported as the startup default; UI selector overrides it at runtime
- Removed `PORT` environment variable from Docker setup (unnecessary given Docker port mapping)

## [0.3.0] - 2026-06-28

### Added

- League-wide schedule grid view (`#schedule-grid`) showing all 32 teams × 18 weeks with opponent abbreviations, home/away indicators, bye weeks, and scores for completed games
- Backend API endpoint `GET /api/schedule-grid` serving structured schedule data
- "Schedule" navigation link in the navbar (between Standings and Statistics)
- Team abbreviation mapping and `get_team_abbreviation()` helper in `nfl_teams.py`
- Property-based tests for the schedule grid: 1 backend (hypothesis) + 5 frontend (fast-check)
- "Weeks completed" and "Games completed" stats on the standings page data panel
- Version number in server startup log message
- README screenshot showing the Ravens' playoff path analysis
- Schedule Grid section in README

### Changed

- Standings data panel: split "Weeks" into "Weeks loaded" / "Weeks completed", split "Games" into "Games loaded" / "Games completed (X%)", removed redundant "Scheduled" counter
- Team detail back link now uses `history.back()` instead of always navigating to standings
- Playoff path analysis: team's own games now highlighted with Bootstrap `table-info` class (visible blue) instead of CSS variable that was overridden by Bootstrap table styles
- Slow parallel simulation integration tests marked with `@pytest.mark.slow` and excluded from default test runs (use `pytest -m slow` to run them explicitly)
- Reduced iteration counts in parallel simulation tests for faster execution when run explicitly

### Fixed

- Game cells in schedule grid no longer link to team detail page (no game detail view exists)
- Playoff path blue row highlighting now visible with Bootstrap table classes

## [0.2.1] - 2026-06-27

### Added

- Tooltip on Iterations control explaining trial count and performance tradeoff
- Tooltip on Cutoff Week control explaining how it determines which games are real vs simulated
- Heatmap coloring on team detail seed distribution table for better visual clarity
- `.numeric-inline` CSS class for right-aligned numbers that stay on the same baseline as surrounding text

### Changed

- Standings column "TB" renamed to full "Tiebreaker" header
- Tiebreaker legend updated to list all 7 possible tiebreaker steps (H2H, Div, Conf, SoV, SoS, Pts, Alpha)
- Seeding probability tables (main and team detail) now use `table-bordered` for clearer cell boundaries
- Playoff path buttons wrapped in flex container to prevent full-width stretching
- Path analysis tables use `width:auto` to shrink-fit content instead of spanning full page width
- Week and Confidence columns in path tables right-aligned with `numeric-inline` for proper vertical alignment

### Fixed

- Playoff path "Team must win" and "Required outcomes" tables no longer stretch across full page width
- Week values in path tables now vertically align with other cells (removed monospace font mismatch)
- Confidence percentages in path tables vertically align with row content

## [0.2.0] - 2026-06-27

### Changed

- Migrated frontend from custom ~500-line CSS to Bootstrap 5.3.3 loaded via CDN
- Replaced custom navbar with Bootstrap `navbar navbar-expand-lg navbar-dark sticky-top` component with responsive collapse
- Converted all tables to Bootstrap `table table-striped table-hover` classes
- Converted all form controls to Bootstrap classes (`form-control`, `form-select`, `form-range`, `btn`)
- Converted content panels from custom `.controls-panel` to Bootstrap `card card-body` components
- Replaced custom notification system with Bootstrap `alert alert-danger/info alert-dismissible fade show` with auto-dismiss
- Replaced custom spinner with Bootstrap `spinner-border text-primary` inside a fixed overlay
- Migrated navigation active state to use Bootstrap `active` class and `aria-current="page"`
- Replaced `.hidden`/`.visible` toggles with Bootstrap `d-none` utility class
- Simulation controls layout now uses Bootstrap `row`/`col` grid for responsive arrangement
- Noise and Workers sliders restructured with label on top, slider below, value text underneath
- Reduced `styles.css` from ~500 lines to ~165 non-comment lines of NFL-specific overrides
- Conference filter buttons now use Bootstrap `btn btn-sm btn-primary`/`btn-outline-primary`
- Disclaimer bar now uses dark text on light background for readability, aligned with container
- Version number in navbar styled smaller with improved contrast against dark background

### Added

- Team logo (28×28) displayed next to team name in the schedule view header
- "Team Str" column in team schedule view showing the team's strength rating at each week
- Legend below schedule table explaining "Opp Str" and "Team Str" values
- `.numeric-left` CSS class for left-aligned monospace cells (used in TB column)
- `.control-field` CSS class for vertical stacking of form labels and inputs
- `.playwright-mcp/` added to `.gitignore`

### Fixed

- Cutoff week dropdown text clipping (changed from fixed `width:110px` to `width:auto;min-width:110px`)
- TB column header/cell size and font mismatch with other standings columns
- Standings table vertical alignment inconsistency across columns
- Tiebreaker display now correctly identifies which NFL tiebreaker step resolved the tie (was only showing H2H or Conf, now shows all 7 steps: H2H, Div, Conf, SoV, SoS, Pts, Alpha)

### Technical

- Bootstrap 5.3.3 CSS and JS loaded via jsDelivr CDN (no npm/build tooling required)
- Custom stylesheet retains only: CSS custom properties, conference border colors, division leader highlighting, game result colors, team link styles, fixed column widths, numeric cell styling, progress overlay, logo sizing
- All 7 JS files updated to emit Bootstrap class names in DOM generation

## [0.1.0] - 2025-06-27

### Added

- Monte Carlo simulation engine with configurable iterations (100–1,000,000), cutoff week, game noise, and tie probability
- Parallel simulation across multiple CPU cores using Python multiprocessing (configurable worker count, near-linear speedup)
- Iterative team strength ratings with strength-of-schedule weighting, relaxation damping for convergence, and Bayesian dampening based on sample size
- Full NFL tiebreaker implementation (head-to-head, division/conference record, common games, strength of victory/schedule, point-based steps for real games, coin toss fallback)
- ESPN public JSON API integration for fetching season schedules, game results, and live game data
- Local SQLite caching with TTL policies (completed games never expire, in-progress 60s, scheduled 24h)
- Interactive browser-based UI with hash-based SPA routing (standings, statistics, results views)
- Standings view grouped by conference and division with team logos, records, and games behind
- Team schedule view with completed/in-progress/scheduled game display
- Simulation results: playoff probabilities, seeding probability matrix, top 50 scenarios
- Playoff path analysis with causality filtering (identifies which game outcomes are needed for a team to make playoffs)
- Guaranteed path solver using constraint-based deterministic search
- Simulation controls with persisted settings (iterations, cutoff week, noise, workers stored in localStorage)
- Version display in UI header read from pyproject.toml via importlib.metadata
- Server logging of simulation timing (workers, elapsed time, throughput)

### Technical

- Python 3.11+ with type hints throughout
- No external runtime dependencies beyond httpx (for ESPN API calls)
- Frontend: plain HTML/CSS/JS, no build step, no external CDN dependencies
- Cross-platform: Linux (tested), macOS and Windows (untested, fork/spawn multiprocessing contexts)
- Property-based test strategies using Hypothesis
- 104 unit/integration tests passing

[Unreleased]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.7.1...HEAD
[0.7.1]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.6.2...v0.7.0
[0.6.2]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/releases/tag/v0.1.0
