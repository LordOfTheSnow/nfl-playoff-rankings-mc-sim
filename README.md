# NFL Monte Carlo Playoff Ranking Simulator

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-green)](LICENSE)
[![Docker Image](https://img.shields.io/badge/ghcr.io-nfl--playoff--rankings--mc--sim-blue?logo=docker)](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/pkgs/container/nfl-playoff-rankings-mc-sim)
[![Build Status](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/actions/workflows/docker-publish.yml)

**v1.0.2**

A web application that predicts NFL playoff probabilities using Monte Carlo simulation. It fetches real game data from ESPN's public API, computes strength-of-schedule-weighted team ratings, simulates remaining games, applies official NFL tiebreaker rules, and presents probability distributions through an interactive browser UI.

> This project is actively maintained; features continue to evolve.

## Features

- Fetch NFL season data from ESPN's public JSON API
- Handles seasons of different lengths (pre-2021: 16 games/17 weeks; 2021+: 17 games/18 weeks) throughout — season shape is derived from the loaded schedule rather than hardcoded, so standings, simulation, schedule grid, and clinching all stay correct for any season year
- Iterative team strength ratings with Bayesian dampening
- Monte Carlo simulation with configurable iterations, cutoff week, game noise, and tie probability (defaults to an empirical estimate from historical seasons, overridable via slider)
- Parallel simulation across multiple CPU cores for faster execution
- Full NFL tiebreaker implementation (head-to-head, division/conference record, strength of victory/schedule, point-based steps) with proper step labeling in standings display
- Interactive standings view with team logos, clinch/division/#1-seed/eliminated status tags, and hover-tooltip tiebreaker explanations
- Team Detail page with a full-season schedule ledger, per-week team strength tracking, and postponed/canceled game handling
- League-wide schedule grid showing all 32 teams x the season's full week range with scores, bye weeks, and postponed/canceled games
- Statistics page: game-outcome rates (home/away/tie/overtime/one-score), score margin distribution, and longest winning/losing streaks
- Simulation results: playoff probabilities, seeding matrix, top scenarios
- Clinching scenarios solver: find all game-outcome combinations that guarantee a playoff spot (available once 4 weeks remain before the season ends — week 14 for an 18-week season)
- CP-SAT constraint solver for mathematical clinching/elimination detection using Google OR-Tools (provably correct, available from week 1)
- Solver performance export: one-click export of timing benchmarks to `doc/solver-performance.md`
- Settings / Info page: SQLite cache database metadata, server runtime environment, recent ESPN fetch attempts, and resettable lifetime run counters (games simulated, clinching resolver evaluations)
- Season selector in the navbar for switching seasons without restarting
- Local SQLite caching with TTL policies
- Entire UI — every page, the app-wide nav, and the Solver Timing History dialog — redesigned in a flat "Modernist" style (Archivo type, red accent, zero corner radius); no Bootstrap dependency remains
- Optional Docker deployment with pre-built multi-architecture images (amd64/arm64) on GHCR

## Screenshots

### Seeding Probabilities — "Modernist" redesign (2025 season, cutoff week 16)

![Seeding Probabilities matrix for AFC and NFC in the Modernist Ledger redesign](/doc/img/screenshot-seeding-probabilities-new-design.png)

*Seeding Probabilities matrix: each cell is tinted on a warm tan-to-maroon scale proportional to that team's probability of landing exactly that seed, switching to white text once the tint gets dark enough — never gray, and never tinted at exactly 0%.*

📸 **[See the full screenshot gallery →](doc/screenshots.md)** — Standings, Team Detail, Schedule Grid, Playoff Probabilities, Top Scenarios, Clinching Scenarios, Solver Timing History, Statistics, and Settings / Info.

## Setup

Requires Python 3.11+. Runs on Linux, macOS, and Windows (macOS and Windows have not been tested yet).

```bash
# Clone the repository
git clone https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim.git
cd nfl-playoff-rankings-mc-sim

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Or with dev/test tools (pytest, hypothesis)
pip install -e ".[dev]"
```

## Usage

```bash
# Activate the virtual environment
source .venv/bin/activate

# Start the server (default: port 8080, current season)
python -m src

# Start with a specific season and port
python -m src --season 2025 --port 8080
```

Then open http://localhost:8080 in your browser.

1. Click **Fetch Data** on the Standings page to pull game data from ESPN
2. View current standings grouped by conference and division, and set the cutoff week if needed
3. Click **Go to Simulations →**, configure simulation parameters (iterations, cutoff week, noise) and click **Simulate**
4. View results on the same **Simulations** page — click any team for candidate details

## Docker (optional)

Docker is entirely optional. The existing pip-based setup (virtual environment + `pip install`) described above remains fully supported and is the recommended workflow for local development.

If you prefer running the app in a container, you can either pull the pre-built image from GitHub Container Registry or build locally:

```bash
# Pull the pre-built image (no build required)
docker pull ghcr.io/lordofthesnow/nfl-playoff-rankings-mc-sim:latest
```

Images are built and published automatically via GitHub Actions whenever a version tag is pushed. Multi-architecture images are provided for `linux/amd64` and `linux/arm64`, so the same tag works on x86 machines and ARM hosts (e.g. Apple Silicon Macs, Raspberry Pi, AWS Graviton).

```bash
# Or build the image locally
docker build -t nfl-playoff-rankings-mc-sim .

# Run with a bind-mounted directory (database persists on your host)
mkdir -p data
docker run -p 8080:8080 -v ./data:/data nfl-playoff-rankings-mc-sim

# Run with a named volume (Docker manages storage)
docker run -p 8080:8080 -v nfl-data:/data nfl-playoff-rankings-mc-sim

# Map to a different host port (app always listens on 8080 inside the container)
docker run -p 9090:8080 -e SEASON=2024 -v nfl-data:/data nfl-playoff-rankings-mc-sim

# Or use Docker Compose (builds, mounts volume, maps port 8080 automatically)
docker compose up
```

The container always listens on port 8080 internally. Use Docker's `-p` flag to map any host port to it (e.g. `-p 9090:8080`). The environment variable `SEASON` (2000-2100) is optional and defaults to the current season. CLI arguments passed after the image name take precedence over environment variables.

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Documentation

- [Screenshot Gallery](doc/screenshots.md) — Every page in the app
- [API Reference](doc/api.md) — All HTTP endpoints, parameters, and response formats
- [Algorithms](doc/algorithms.md) — Team strength ratings, clinching scenarios solver, CP solver
- [Technical](doc/technical.md) — Parallel simulation, solver performance export
- [Solver Performance](doc/solver-performance.md) — Cross-platform benchmark results
- [Clinching Solver Consolidation](doc/clinching-solver-consolidation.md) — Investigation notes on duplicated game-simulation logic between the main simulator and the clinching solver

## ToDo

- **Reduce impact-games computation cost**: Profiling (see [Technical docs](doc/technical.md#where-time-goes-profiling-findings)) found the per-team "Top 5 Impact Games" analysis — not the main Monte Carlo loop — dominates simulation wall-clock time (~90-98% at the default 10,000 iterations), since it runs its own nested mini-simulations per relevant game per team, roughly independent of the main iteration count. Investigate cheaper sampling (fewer/smarter mini-trials) or more effective parallelization.
- **Vectorize standings computation with NumPy** *(lower priority than previously assumed — see [profiling notes](doc/technical.md#where-time-goes-profiling-findings))*: Rewrite the MC simulation hot path to process all trials simultaneously as batched array operations. Game outcome simulation (random draws + strength comparisons) and W/L/T record accumulation can be expressed as matrix operations over a `(trials, games)` array, eliminating per-trial Python loops. The tiebreaker logic would remain in Python but only be invoked for the subset of trials where teams are actually tied in win percentage. At the current default iteration count, the main trial loop is a small fraction of total time next to impact-games computation (above), so this pays off mainly at much higher iteration counts (~100,000+) where the main loop's linearly-scaling cost catches up — re-profile at that scale before committing to the rewrite.
- **Consolidate duplicate divisional tiebreaker logic**: `server.py`'s `GET /api/standings` handler (`_division_tiebreak_sort`) reimplements the NFL tiebreaker cascade independently of `standings.py`'s `break_tie`/`_apply_tiebreaker_steps` (the documented single source of truth used by `determine_playoff_bracket`), purely to compute display row order and the `tiebreaker` badge text. The two can disagree on a fully unresolved tie: the real engine's coin-toss fallback (`_step_coin_toss`) can crown a different division champion than the display's alphabetical fallback picks as the first row. Have the standings endpoint reuse `standings.py`'s tiebreaker results directly instead of re-deriving its own.

## Disclaimer

This is an independent project not affiliated with the NFL or any official NFL service. All data is sourced from publicly available APIs.

Simulation results are probabilistic estimates, not guarantees — they may be incomplete, delayed, or inaccurate. This software is provided "as is", without warranty of any kind; use it at your own risk. Relying on these results (e.g. for betting or other decisions) is done entirely at your own risk, and the author(s) accept no liability for any damages or losses arising from such use.
