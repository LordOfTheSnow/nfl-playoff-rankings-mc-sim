# NFL Playoff Rankings Monte Carlo Simulator

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-green)](LICENSE)
[![Docker Image](https://img.shields.io/badge/ghcr.io-nfl--playoff--rankings--mc--sim-blue?logo=docker)](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/pkgs/container/nfl-playoff-rankings-mc-sim)
[![Build Status](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/actions/workflows/docker-publish.yml)

**v1.5.0**

A browser application that predicts NFL playoff probabilities using Monte Carlo simulation. It fetches real game data from ESPN's public API, computes strength-of-schedule-weighted team ratings, simulates remaining games, applies official NFL tiebreaker rules, and presents probability distributions through an interactive browser UI.

> This project is actively maintained; features continue to evolve.

## Features

- Monte Carlo simulation with configurable iterations, cutoff week, game noise, and tie probability (defaults to an empirical estimate from historical seasons, overridable via slider)
- Fetch NFL season data from ESPN's public JSON API
- Iterative team strength ratings with Bayesian dampening
- Full NFL tiebreaker implementation (head-to-head, division/conference record, strength of victory/schedule, point-based steps) with proper step labeling in standings display
- Simulation results: playoff probabilities, seeding matrix, top scenarios
- Clinching scenarios solver: find all game-outcome combinations that guarantee a playoff spot (available once 4 weeks remain before the season ends — week 14 for an 18-week season)
- CP-SAT constraint solver for mathematical clinching/elimination detection using Google OR-Tools (provably correct, available from week 1)
- Wild Card Round view: top-7 seeds per conference as 2v7/3v6/4v5 matchups, the #1 seed's first-round bye, and an "In the Hunt" list for teams below seed 7 still alive — from either Actual standings or Simulated (most-likely) seeding, with per-team last-5 game log, current streak, and strength rating
- Handles seasons of different lengths (pre-2021: 16 games/17 weeks; 2021+: 17 games/18 weeks) throughout — season shape is derived from the loaded schedule rather than hardcoded, so standings, simulation, schedule grid, and clinching all stay correct for any season year
- Parallel simulation across multiple CPU cores for faster execution
- Simulation runs as a background job with live progress (current phase, e.g. "Ranking impact games… (312/876)") and a Cancel button for stopping a long run early
- Interactive standings view with team logos, clinch/division/#1-seed/eliminated status tags, and hover-tooltip tiebreaker explanations
- Team Detail page with a full-season schedule ledger, per-week team strength tracking, and postponed/canceled game handling
- League-wide schedule grid showing all 32 teams x the season's full week range with scores, bye weeks, and postponed/canceled games
- Statistics page: game-outcome rates (home/away/tie/overtime/one-score), score margin distribution, and longest winning/losing streaks
- Settings / Info page: SQLite cache database metadata, server runtime environment, recent ESPN fetch attempts, and resettable lifetime run counters (games simulated, clinching resolver evaluations)
- Season selector in the navbar for switching seasons without restarting
- HTML export: save the current Standings, Statistics, Schedule Grid, Simulation, and Wild Card Round results as a standalone HTML page, or a ZIP bundle with an index and one page per team
- Teaser image: a "Biggest movers" PNG from the Export page for link previews and social posts, in landscape (1200×630), portrait 4:5 (1080×1350) or 9:16 Story (1080×1920) format, showing the five teams whose playoff probability changed most since a baseline you saved explicitly (so week-over-week deltas stay pinned to the numbers you published), with team logos and the app name and version
- Wild Card teaser images: a 9:16 Story PNG per conference (AFC/NFC) showing the projected Wild Card bracket from your last simulation run — the #1 seed's bye, the three matchups, and the favorite in each
- Matchups teaser image: a 9:16 Story PNG from the Export page listing every game in the upcoming week with its simulated home/away/tie win probability as a stacked bar (or the final score for games already played when the cutoff week is only partly done), team logos, and automatic color disambiguation when two teams in the same matchup share a color family
- Solver performance export: one-click export of timing benchmarks to `doc/solver-performance.md`
- Local SQLite caching with TTL policies
- Optional Docker deployment with pre-built multi-architecture images (amd64/arm64) on GHCR

## Screenshots

### Playoff Probabilities and Seeding Probabilities (2026 season, cutoff week 6)

![Simulation results showing Playoff Probabilities and Seeding Probabilities matrix for AFC and NFC](/doc/img/screenshot-simulation-results.png)

*Playoff Probabilities tables for both conferences, each row with an inline probability bar and the 7th seed (the projected playoff cutoff) highlighted, followed by the Seeding Probabilities matrix: each cell is tinted on a warm tan-to-maroon scale proportional to that team's probability of landing exactly that seed, switching to white text once the tint gets dark enough — never gray, and never tinted at exactly 0%.*

📸 **[See the full screenshot gallery →](doc/screenshots.md)** — Standings, Team Detail, Schedule Grid, Playoff Probabilities, Top Scenarios, Clinching Scenarios, Solver Timing History, Statistics, Wild Card Round, Teaser Images, and Settings / Info.

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

## Windows desktop app (optional)

Every release from v1.5.0 on includes an experimental Windows build, `nfl-playoff-rankings-mc-sim-vX.Y.Z-windows-x64.zip`, on its [GitHub Releases](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/releases) page. It doesn't need Python or Docker, but uses the browser to display the app's frontend:

1. Download the ZIP and extract it anywhere (e.g. your Desktop).
2. Run `nfl-playoff-rankings-mc-sim.exe` in the extracted `nfl-playoff-rankings-mc-sim` folder.

The app opens in your default browser at `http://127.0.0.1:8765/`, plus a small control window that keeps it running:

![Windows control window showing the app's URL, a port field with Apply, and Open in browser, Open data folder and Quit buttons](/doc/img/screenshot-windows-app-starter.png)

- **Port:** change the port and click **Apply** if 8765 is taken or you prefer another one. The app restarts on that port, reopens the browser and remembers the choice. Simulation results shown at the old address are lost.
- **Open in browser:** reopens the app if you closed its tab.
- **Open data folder:** opens the folder with the cache and `app.log`.
- **Quit**, or closing the window, stops the app. Closing the browser tab does not.

Starting the exe again while the app is running just opens the browser on it.

**The build is not code-signed**, so on first launch Windows SmartScreen may show "Windows protected your PC". Click **More info → Run anyway**.

- **Requirements:** Windows 10/11 x64 and any current browser.
- **Data:** the cache database (`nfl_cache.db`), the log file (`app.log`), the saved port (`settings.json`) and solver-performance exports are stored in `%LOCALAPPDATA%\nfl-playoff-rankings-mc-sim\`. They survive upgrading to a new release (extract the new ZIP and delete the old folder).
- The app's server listens only on `127.0.0.1`, so it is not reachable from other machines and triggers no firewall prompt.

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
- [Technical](doc/technical.md) — Parallel simulation, solver performance export, Windows desktop build
- [Solver Performance](doc/solver-performance.md) — Cross-platform benchmark results
- [Clinching Solver Consolidation](doc/clinching-solver-consolidation.md) — Investigation notes on duplicated game-simulation logic between the main simulator and the clinching solver

## ToDo

- **Vectorize standings computation with NumPy** *(lower priority than previously assumed — see [profiling notes](doc/technical.md#where-time-goes-profiling-findings))*: Rewrite the MC simulation hot path to process all trials simultaneously as batched array operations. Game outcome simulation (random draws + strength comparisons) and W/L/T record accumulation can be expressed as matrix operations over a `(trials, games)` array, eliminating per-trial Python loops. The tiebreaker logic would remain in Python but only be invoked for the subset of trials where teams are actually tied in win percentage. At the current default iteration count, the main trial loop is a small fraction of total time next to impact-games computation (still the dominant cost even after the mitigations in [Algorithms](doc/algorithms.md#impact-games--background-jobs)), so this pays off mainly at much higher iteration counts (~100,000+) where the main loop's linearly-scaling cost catches up — re-profile at that scale before committing to the rewrite.

## Disclaimer

This is an independent project not affiliated with the NFL or any official NFL service. All data is sourced from publicly available APIs.

Simulation results are probabilistic estimates, not guarantees — they may be incomplete, delayed, or inaccurate. This software is provided "as is", without warranty of any kind; use it at your own risk. Relying on these results (e.g. for betting or other decisions) is done entirely at your own risk, and the author(s) accept no liability for any damages or losses arising from such use.
