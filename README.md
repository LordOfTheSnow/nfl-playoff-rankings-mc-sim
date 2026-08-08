# NFL Monte Carlo Playoff Ranking Simulator

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-green)](LICENSE)
[![Docker Image](https://img.shields.io/badge/ghcr.io-nfl--playoff--rankings--mc--sim-blue?logo=docker)](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/pkgs/container/nfl-playoff-rankings-mc-sim)
[![Build Status](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/actions/workflows/docker-publish.yml)

**v0.7.4**

A web application that predicts NFL playoff probabilities using Monte Carlo simulation. It fetches real game data from ESPN's public API, computes strength-of-schedule-weighted team ratings, simulates remaining games, applies official NFL tiebreaker rules, and presents probability distributions through an interactive browser UI.

> **Work in Progress** — This project is under active development. Features may change and some functionality is incomplete.

## Features

- Fetch NFL season data from ESPN's public JSON API
- Iterative team strength ratings with Bayesian dampening
- Monte Carlo simulation with configurable iterations, cutoff week, and game noise
- Parallel simulation across multiple CPU cores for faster execution
- Full NFL tiebreaker implementation (head-to-head, division/conference record, strength of victory/schedule, point-based steps) with proper step labeling in standings display
- Interactive standings view with team logos, clinch/division/#1-seed/eliminated status tags, and hover-tooltip tiebreaker explanations
- League-wide schedule grid showing all 32 teams x 18 weeks with scores and bye weeks
- Team schedule view with bye week display and per-week team strength tracking
- Simulation results: playoff probabilities, seeding matrix, top scenarios
- Clinching scenarios solver: find all game-outcome combinations that guarantee a playoff spot (available after week 14)
- CP-SAT constraint solver for mathematical clinching/elimination detection using Google OR-Tools (provably correct, available from week 1)
- Solver performance export: one-click export of timing benchmarks to `doc/solver-performance.md`
- Season selector in the navbar for switching seasons without restarting
- Local SQLite caching with TTL policies
- Standings, Team Detail, and Simulation Results pages, plus the app-wide nav, redesigned in a flat "Modernist" style (Archivo type, red accent, zero corner radius); Schedule Grid and Statistics still use the original Bootstrap 5.3.8 (CDN) styling
- Settings / Info page showing SQLite cache database metadata (seasons stored, per-season completeness, and the last 20 ESPN fetch attempts with failures flagged), the server's runtime environment (CPU model/cores, Python version, platform), and lifetime totals for games simulated and clinching resolver evaluations performed

## Screenshots

### Standings page — "Modernist" redesign (2025 season, cutoff week 17)

![Standings page in the Modernist Ledger redesign, 2025 season, week 17 cutoff](/doc/img/screenshot-standings-new-design.png)

*Standings page in the new flat, red-on-white "Modernist Ledger" design. Each team row shows a status tag — DIVISION, #1 SEED, CLINCHED, or ELIMINATED — and, when a standings tie was resolved by a tiebreaker rule, a chip (e.g. "H2H 2-0") that explains why on hover.*

<a id="team-detail-screenshot"></a>
### Team Detail page — "Modernist" redesign (2025 season)

![Team Detail page in the Modernist Ledger redesign, showing the New England Patriots' full 2025 season schedule](/doc/img/screenshot-team-new-design.png)

*Team Detail page in the same flat "Modernist Ledger" style as Standings, reusing the same ledger table component. Each completed game shows a bordered Win/Loss/Tie tag, and the bye week renders as a single italic row.*

### Simulation Results page — "Modernist" redesign (2025 season, cutoff week 16)

![Playoff Probabilities tables for AFC and NFC in the Modernist Ledger redesign](/doc/img/screenshot-playoff-probabilities-new-design.png)

*Playoff Probabilities tables for both conferences. Each row shows an inline probability bar, and the 7th seed — the current projected playoff cutoff — is highlighted with the same leader-row treatment used for division leaders in Standings.*

![Seeding Probabilities matrix for AFC and NFC in the Modernist Ledger redesign](/doc/img/screenshot-seeding-probabilities-new-design.png)

*Seeding Probabilities matrix: each cell is tinted on a warm tan-to-maroon scale proportional to that team's probability of landing exactly that seed, switching to white text once the tint gets dark enough — never gray, and never tinted at exactly 0%. The collapsed Top Scenarios accordion sits below.*

![Top Playoff Scenarios table expanded in the Modernist Ledger redesign](/doc/img/screenshot-top-10-mlploff-scens-new-design.png)

*The Top Scenarios accordion expanded, ranking the most likely distinct AFC/NFC seeding combinations by probability.*

<a id="clinching-scenarios-screenshot"></a>
### Clinching Scenarios — "Modernist" redesign (Detroit Lions, 2025 season)

![Clinching Scenarios for the Detroit Lions in the Modernist Ledger redesign](/doc/img/screenshot-playoff-probabilities-team-new-design.png)

*Team Detail panel (opened by clicking a team on the Results page) showing every game-outcome combination that guarantees or eliminates a playoff spot, grouped by remaining record. Conditions for every scenario in a group share one aligned table, with a rowspan'd `#` column tying each scenario's rows together instead of giving every scenario its own separately-sized table.*

### Settings / Info page — "Modernist" style

![Settings / Info page in the Modernist style, showing runtime environment, lifetime totals, SQLite cache database metadata, and recent fetch attempts](/doc/img/screenshot-settings-info-new-design.png)

*Settings / Info page: server runtime environment (CPU model/cores, Python version, platform, and the distinct worker start methods used by simulation vs. the clinching resolver), lifetime totals for games simulated and clinching resolver evaluations, per-season SQLite cache completeness, and the 20 most recent ESPN fetch attempts with failures flagged.*

## Schedule Grid

The Schedule view (`#schedule-grid`) provides a compact league-wide overview of the entire NFL season. All 32 teams are displayed as rows, sorted alphabetically by abbreviation, with weeks 1-18 as columns.

**Cell contents:**
- **Home games**: opponent abbreviation (e.g., "MIA")
- **Away games**: "@" prefix (e.g., "@MIA")
- **Bye weeks**: "BYE" in muted text
- **Completed/in-progress games**: score displayed below the opponent (e.g., "24-17")

Each team's name in the first column links to their detailed schedule page. The grid uses a compact font (0.75rem) and minimal padding so all 19 columns fit on screens 1280px or wider, with horizontal scrolling on smaller viewports.

The grid data is served by `GET /api/schedule-grid`, which returns all 32 teams with their 18-week matchup arrays (opponent abbreviation, home/away flag, game status, and scores).

## Team Detail Page

*See [the screenshot above](#team-detail-screenshot) for what this looks like.*

The Team Detail view (`#team/<name>`, linked from every team name in Standings and the Schedule Grid) shows one team's full-season schedule as a ledger table, reusing the same `.mdn-led-table` component as the Standings page.

**Columns:** Week, Opponent, Opp Str (the opponent's strength rating that week), Home/Away, Score, Result/Status, Team Str (this team's strength rating that week — both ratings are recalculated weekly, so they shift as the season progresses).

**Result/Status column:**
- Completed games show a bordered tag: **Win** (accent-red border), **Loss** (dark neutral border, styled the same as the Standings ELIMINATED badge), or **Tie** (dashed border, italic)
- In-progress games show the current quarter and clock
- Scheduled games show the kickoff date
- The bye week renders as a single italic "BYE WEEK" row spanning the remaining columns

Data is served by `GET /api/team/{name}`, which returns the team's current record and all of its games for the season; the bye week is inferred client-side from the missing week number rather than returned explicitly by the API.

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
2. View current standings grouped by conference and division
3. Configure simulation parameters (iterations, cutoff week, noise) and click **Simulate**
4. View results on the **Results** page — click any team for details

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

- [API Reference](doc/api.md) — All HTTP endpoints, parameters, and response formats
- [Algorithms](doc/algorithms.md) — Team strength ratings, clinching scenarios solver, CP solver
- [Technical](doc/technical.md) — Parallel simulation, solver performance export
- [Solver Performance](doc/solver-performance.md) — Cross-platform benchmark results

## ToDo

- **Massive UI overhaul**: The current interface is functional but needs a ground-up redesign for better usability, visual polish, and information hierarchy. Standings, Team Detail, and Simulation Results have been redesigned in the "Modernist" flat/red-on-white style (see `design_handoff_standings_redesign/`); Schedule Grid and Statistics still use the old Bootstrap look.
- **Vectorize standings computation with NumPy**: Rewrite the MC simulation hot path to process all trials simultaneously as batched array operations. Game outcome simulation (random draws + strength comparisons) and W/L/T record accumulation can be expressed as matrix operations over a `(trials, games)` array, eliminating per-trial Python loops. The tiebreaker logic would remain in Python but only be invoked for the subset of trials where teams are actually tied in win percentage. Expected 5-15x overall speedup for the simulation pipeline.

## Disclaimer

This is an independent project not affiliated with the NFL or any official NFL service. All data is sourced from publicly available APIs.
