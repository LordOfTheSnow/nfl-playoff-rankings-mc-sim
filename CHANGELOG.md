# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/releases/tag/v0.1.0
