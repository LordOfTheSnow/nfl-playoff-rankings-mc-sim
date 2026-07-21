# NFL Monte Carlo Playoff Ranking Simulator

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-green)](LICENSE)
[![Docker Image](https://img.shields.io/badge/ghcr.io-nfl--playoff--rankings--mc--sim-blue?logo=docker)](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/pkgs/container/nfl-playoff-rankings-mc-sim)
[![Build Status](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/actions/workflows/docker-publish.yml)

**v0.6.1**

A web application that predicts NFL playoff probabilites using Monte Carlo simulation. It fetches real game data from ESPN's public API, computes strength-of-schedule-weighted team ratings, simulates remaining games, applies official NFL tiebreaker rules, and presents probability distributions through an interactive browser UI.

> **Work in Progress** — This project is under active development. Features may change and some functionality is incomplete.

## Features

- Fetch NFL season data from ESPN's public JSON API
- Iterative team strength ratings with Bayesian dampening
- Monte Carlo simulation with configurable iterations, cutoff week, and game noise
- Parallel simulation across multiple CPU cores for faster execution
- Full NFL tiebreaker implementation (head-to-head, division/conference record, strength of victory/schedule, point-based steps) with proper step labeling in standings display
- Interactive standings view with team logos and tiebreaker annotations
- League-wide schedule grid showing all 32 teams × 18 weeks with scores and bye weeks
- Team schedule view with bye week display and per-week team strength tracking
- Simulation results: playoff probabilities, seeding matrix, top scenarios
- Clinching scenarios solver: find all game-outcome combinations that guarantee a playoff spot (available after week 14)
- CP-SAT constraint solver for mathematical clinching/elimination detection using Google OR-Tools (provably correct, available from week 1)
- Season selector in the navbar for switching seasons without restarting
- Local SQLite caching with TTL policies
- Responsive UI built on Bootstrap 5.3.3 (CDN) with NFL-branded styling

## Screenshots

### Simulation results (2025 season)

![Clinching Scenarios for the Detroit Lions](/doc/img/screenshot-clinching-scenarios.png)

*Clinching scenarios for the Detroit Lions — season 2025, cutoff week 15, showing all paths to the playoffs grouped by remaining record.*

### Standings page (2025 season, cutoff week 16)

![Standings after week 16, 2025](/doc/img/screenshot-standings.png)

*Standings page after week 16 of the 2025. Note the clinching or elimination badges next to the teams already qualified for the playoffs or eliminated.

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

# Run with a bind mount (database file persists on your host)
docker run -p 8080:8080 -v ./nfl_cache.db:/data/nfl_cache.db nfl-playoff-rankings-mc-sim

# Run with a named volume (Docker manages storage)
docker run -p 8080:8080 -v nfl-data:/data nfl-playoff-rankings-mc-sim

# Map to a different host port (app always listens on 8080 inside the container)
docker run -p 9090:8080 -e SEASON=2024 -v nfl-data:/data nfl-playoff-rankings-mc-sim

# Or use Docker Compose (builds, mounts volume, maps port 8080 automatically)
docker compose up
```

The container always listens on port 8080 internally. Use Docker's `-p` flag to map any host port to it (e.g. `-p 9090:8080`). The environment variable `SEASON` (2000–2100) is optional and defaults to the current season. CLI arguments passed after the image name take precedence over environment variables.

## Team Strength Ratings

The simulator computes team strength using an iterative strength-of-schedule algorithm. Ratings reflect not just win percentage, but the quality of opponents beaten.

### Algorithm

1. Initialize all teams with win-percentage-based ratings (normalized to average 1.0)
2. For each iteration:
   - Compute each team's new rating as a weighted win ratio: wins against strong opponents count more than wins against weak ones
   - Rating = (sum of opponent ratings for wins) / (sum of all opponent ratings)
   - Ties contribute half credit
3. Normalize ratings so the league average stays at 1.0
4. Apply relaxation: blend 50% new ratings with 50% previous ratings to prevent oscillation
5. Check convergence: if max |new − old| < 0.001, stop

The relaxation step is critical. Without it, the interdependent ratings form feedback loops (beating a strong team raises your rating, which raises theirs for having played you) that cause oscillation rather than convergence.

### Bayesian dampening

After convergence, ratings are dampened toward the league average (1.0) based on sample size:

```
dampened = (games / (games + K)) * raw_rating + (K / (games + K)) * 1.0
```

With K=8 (default):
- 2 games played → 80% average, 20% calculated (mostly regression to mean)
- 8 games played → 50/50 blend
- 17 games (full season) → 68% calculated, 32% average

This prevents unrealistic extreme ratings early in the season when a 2-0 start against weak opponents could otherwise produce inflated playoff probabilities.

### Output

Ratings are normalized so the average across all teams is 1.0. A rating of 1.5 means that team is estimated to be 50% stronger than average; 0.7 means 30% weaker. These ratings are used as inputs to the Monte Carlo simulation to set win probabilities for unplayed games.

## Parallel Simulation

Monte Carlo simulations are "embarrassingly parallel" — each trial is completely independent. The simulator distributes iteration batches across multiple CPU cores using Python's `multiprocessing`, achieving near-linear speedup.

### How it works

1. The total iteration count is split into equal batches (one per worker process)
2. Each worker process runs its batch independently with its own random number generator
3. When all workers finish, their results (playoff counts, seeding matrices, scenario counters) are merged by summing
4. Impact games analysis also runs in parallel (one team per worker)

### Configuration

The **Workers** slider in the UI controls how many CPU cores to use. It defaults to the machine's total core count and is capped at that value. Setting it to 1 disables parallelism entirely (useful for debugging).

### Performance

On a 4-core machine with 10,000 iterations:

| Workers | Time | Speedup |
|---------|------|---------|
| 1 | ~8.4s | 1.0x |
| 2 | ~5.0s | 1.7x |
| 4 | ~4.0s | 2.1x |

Sub-linear scaling is expected due to process startup overhead and result merging. The speedup improves with higher iteration counts where per-trial work dominates the fixed overhead.

### Platform notes

On Linux, worker processes are created via `fork` (fast, copy-on-write memory). On Windows, `spawn` is used (slightly slower startup since each worker re-imports modules). Both produce identical simulation results.

## Schedule Grid

The Schedule view (`#schedule-grid`) provides a compact league-wide overview of the entire NFL season. All 32 teams are displayed as rows, sorted alphabetically by abbreviation, with weeks 1–18 as columns.

### Cell contents

- **Home games**: opponent abbreviation (e.g., "MIA")
- **Away games**: "@" prefix (e.g., "@MIA")
- **Bye weeks**: "BYE" in muted text
- **Completed/in-progress games**: score displayed below the opponent (e.g., "24-17")

Each team's name in the first column links to their detailed schedule page. The grid uses a compact font (0.75rem) and minimal padding so all 19 columns fit on screens 1280px or wider, with horizontal scrolling on smaller viewports.

### Backend

The grid data is served by `GET /api/schedule-grid`, which returns all 32 teams with their 18-week matchup arrays (opponent abbreviation, home/away flag, game status, and scores). The endpoint transforms cached game data into the grid structure in a single pass.

## Clinching Scenarios Solver

When viewing simulation results, clicking a team with playoff probability between 0% and 100% shows a "Clinching Scenarios" button. This computes all minimal sets of game-outcome conditions that guarantee the team a playoff spot. Available after week 14 only.

### How it works

1. Identifies contenders: same-conference teams not mathematically eliminated
2. Prunes to relevant games: any remaining game where at least one team is a contender
3. Groups results by the target team's own remaining record (e.g., 3-1, 2-2, 1-3)
4. For each possible team record, finds all qualifying universes:
   - If relevant other games ≤ 13: full enumeration (3 outcomes per game: win/loss/tie)
   - If > 13: strength-weighted Monte Carlo sampling (10,000 trials per game-level combination), labeled as non-exhaustive
5. Reduces each qualifying universe to a strictly minimal condition set (every condition is necessary — removing any one breaks the guarantee)
6. Deduplicates and sorts by fewest conditions first

### How to read the results

- Results are grouped by the team's possible finish (e.g., "Finish 3-1" means the team wins 3 and loses 1 of their remaining games)
- Each scenario within a group lists the specific other-game outcomes required
- **Fewer conditions = simpler path** — scenarios are sorted simplest first
- **"No path to playoffs"** means no combination of other results can save the team with that record
- **"Clinches regardless"** means the team's own record alone is enough, no matter what else happens

### Limitations

- Only available after week 14 (hard gate) — earlier in the season the game space is too large for useful results
- When Monte Carlo sampling is used (> 13 relevant games), results may not be exhaustive
- Ties are included as possible outcomes, which increases the combinatorial space

## CP Solver — Mathematical Clinching & Elimination

The CP solver uses [Google OR-Tools CP-SAT](https://developers.google.com/optimization/cp/cp_solver) to determine whether an NFL team has **mathematically clinched** or been **mathematically eliminated** from playoff contention. Unlike the Monte Carlo simulation (which estimates probabilities) or the clinching scenarios solver (which enumerates paths after week 14), the CP solver provides deterministic, provably correct answers — available from week 1 onward.

### What it answers

- **Clinched**: No possible combination of remaining game outcomes can prevent this team from making the playoffs.
- **Eliminated**: No possible combination of remaining game outcomes can result in this team making the playoffs.
- **Alive**: Neither clinched nor eliminated — the team's fate still depends on future results.

### The hybrid approach

NFL tiebreakers are deeply conditional (head-to-head, common games, strength of victory, division/conference record, net points — roughly 11 steps). Encoding them as linear constraints would be impractical. Instead the solver uses a **hybrid strategy**:

1. **CP-SAT handles the arithmetic** — win/loss/tie counts, record bounds, and simple dominance relationships are modeled as integer constraints.
2. **The existing standings engine handles tiebreakers** — for each candidate assignment that passes CP-SAT filtering, the full `compute_standings()` + `determine_playoff_bracket()` pipeline validates whether the target team actually makes or misses the bracket.
3. **Best of both worlds** — CP-SAT's constraint propagation prunes impossible record combinations early, while the standings engine handles the complex conditional logic that constraints can't express.

### Why it's fast (3.4 × 10³⁰ → 28ms)

At cutoff week 14, there are 64 remaining games. Brute-force enumeration would require checking 3⁶⁴ ≈ 3.4 × 10³⁰ possible outcome combinations. The solver finishes in tens of milliseconds through three key techniques:

#### 1. Record Group Decomposition

Instead of exploring the full outcome space, the solver decomposes by the target team's possible final record. With 4 remaining games, there are only 15 possible final records (the formula is (N+1)(N+2)/2). Each record becomes a separate, tractable subproblem: "Given team X finishes 10-7, is there ANY assignment of the other 60 games where they miss/make the playoffs?"

#### 2. CP-SAT Constraint Propagation

Each subproblem has ~64 game variables (domain {0,1,2}). CP-SAT doesn't enumerate them — it propagates constraints:
- **W + L + T = 17** for every team arithmetically locks many variables
- **Target team record is fixed** — e.g., Panthers must finish 10-7-0, so their 4 game outcomes are heavily constrained
- **Dominance bounds** prune teams that can't possibly reach 7th place by wins alone

Through arc consistency and domain reduction, OR-Tools eliminates vast swaths of the search space without generating a single solution. Many record groups are proved **INFEASIBLE** instantly via propagation alone.

#### 3. Early Termination

The solver needs exactly **one witness** to answer each question:
- **Elimination check**: finds one assignment where the team makes playoffs → not eliminated (stop)
- **Clinch check**: finds one assignment where the team misses playoffs → not clinched (stop)

In practice, this means most teams are resolved in 1–2 record groups out of 15+.

#### Real example

| Metric | Value |
|--------|-------|
| Season 2025, cutoff week 16 | All 32 teams |
| Remaining games per team | 2 (32 total conference games) |
| Brute-force space | 3³² ≈ 1.85 × 10¹⁵ |
| Total solve time | 0.3 seconds |
| Method | 2 CP-SAT Solve() calls per team, pure infeasibility |

### API endpoints

- `GET /api/cp-clinch/{team}?cutoff_week=N&time_limit=S` — single team clinch/elimination status
- `GET /api/cp-clinch-all?cutoff_week=N` — all 32 teams, grouped by conference

### Frontend integration

When viewing standings, clinch/elimination badges appear inline next to team names:
- **x** (green) — clinched playoff spot
- **e** (red) — eliminated from contention
- **?** (grey) — solver timed out (inconclusive)

Click a badge to see solver details (solve time, variables, magic number). The badges respect the cutoff week selector — changing the cutoff re-computes standings and badges to show the state at that point in the season.

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## ToDo

(none currently)

## Disclaimer

This is an independent project not affiliated with the NFL or any official NFL service. All data is sourced from publicly available APIs.
