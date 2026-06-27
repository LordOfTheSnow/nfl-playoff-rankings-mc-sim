# NFL Monte Carlo Playoff Ranking Simulator

**v0.2.1**

A web application that predicts NFL playoff probabilites using Monte Carlo simulation. It fetches real game data from ESPN's public API, computes strength-of-schedule-weighted team ratings, simulates remaining games, applies official NFL tiebreaker rules, and presents probability distributions through an interactive browser UI.

> **Work in Progress** — This project is under active development. Features may change and some functionality is incomplete.

## Features

- Fetch NFL season data from ESPN's public JSON API
- Iterative team strength ratings with Bayesian dampening
- Monte Carlo simulation with configurable iterations, cutoff week, and game noise
- Parallel simulation across multiple CPU cores for faster execution
- Full NFL tiebreaker implementation (head-to-head, division/conference record, strength of victory/schedule, point-based steps) with proper step labeling in standings display
- Interactive standings view with team logos and tiebreaker annotations
- Team schedule view with bye week display and per-week team strength tracking
- Simulation results: playoff probabilities, seeding matrix, top scenarios
- Local SQLite caching with TTL policies
- Responsive UI built on Bootstrap 5.3.3 (CDN) with NFL-branded styling
- No external runtime dependencies beyond httpx (for ESPN API calls)

## Setup

Requires Python 3.11+. Runs on Linux, macOS, and Windows (macOS and Windows have not been tested yet).

```bash
# Clone the repository
git clone https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim.git
cd nfl-playoff-rankings-mc-sim

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (including dev/test dependencies)
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

## Playoff Path Analysis

When viewing simulation results, clicking a team with < 75% playoff probability shows an "Analyze Playoff Path" button. This runs a focused mini-simulation with causality filtering to determine what game outcomes are needed for that team to make the playoffs.

### How to read the results

- **Games highlighted in blue** are the team's own games (must-wins)
- **Other games** show which competitors need to lose
- **Confidence %** shows how often that outcome appeared across all qualifying trials:
  - **100%** = happened in every qualifying trial — essentially mandatory
  - **75–99%** = needed in most paths, but a few alternative routes exist without it
  - **60–75%** = helpful in the majority of paths, but other game outcomes can compensate

If a game shows 76.5% confidence, it means in 23.5% of qualifying trials the opposite result happened but the team still made the playoffs through a different combination of other results.

### Causality filtering

Only games where flipping the outcome would actually change the team's playoff status are shown. This filters out correlation artifacts (e.g., "strong team beats weak team" outcomes that happen frequently regardless of their relevance to the target team).

Note: For very low-probability teams (< 2%), the analysis is based on few qualifying trials and may be less stable. More iterations in the main simulation produce more reliable path data.

## Guaranteed Path Solver

In addition to the statistical path analysis, the app includes a deterministic "Find Guaranteed Path" solver. This uses a constraint-based approach (not Monte Carlo) to find the **minimal set of game outcomes** that guarantees the team a playoff spot.

### How it works

1. Assumes the team wins all their remaining games
2. Checks if that alone is enough to clinch (if so, no help needed)
3. If not, iteratively searches for the smallest combination of competitor losses that guarantees qualification
4. Verifies each candidate using the full standings engine with tiebreakers

### How to read the results

- **"Team must win all remaining games"** — the team's own games are always required
- **"Other required results"** — specific games where a competitor must lose, shown with both the required winner and the required loser
- **"✓ Verified"** — the combination has been tested against the standings engine; if all these outcomes happen, the team is guaranteed a playoff spot regardless of all other game results

### Limitations

- The solver searches up to 6 forced outcomes (combinatorial search). If a team needs 7+ specific competitor losses, it reports that a path exists but is too complex to enumerate
- Very early-season cutoffs (many weeks remaining) may have too many combinations to search efficiently
- The solver assumes the team wins ALL remaining games — it doesn't find paths where the team can afford a loss

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## ToDo

(none currently)

## Disclaimer

This is an independent project not affiliated with the NFL or any official NFL service. All data is sourced from publicly available APIs.
