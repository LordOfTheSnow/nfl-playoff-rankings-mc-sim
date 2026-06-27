# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/releases/tag/v0.1.0
