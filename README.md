# NFL Monte Carlo Playoff Ranking Simulator

A web application that predicts NFL playoff probabilites using Monte Carlo simulation. It fetches real game data from ESPN's public API, computes strength-of-schedule-weighted team ratings, simulates remaining games, applies official NFL tiebreaker rules, and presents probability distributions through an interactive browser UI.

> **Work in Progress** — This project is under active development. Features may change and some functionality is incomplete.

## Features

- Fetch NFL season data from ESPN's public JSON API
- Iterative team strength ratings with Bayesian dampening
- Monte Carlo simulation with configurable iterations, cutoff week, and game noise
- Full NFL tiebreaker implementation (head-to-head, division/conference record, strength of victory/schedule, point-based steps)
- Interactive standings view with team logos and tiebreaker annotations
- Team schedule view with bye week display
- Simulation results: playoff probabilities, seeding matrix, top scenarios
- Local SQLite caching with TTL policies
- No external dependencies at runtime (all assets served locally)

## Setup

Requires Python 3.11+.

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/nfl-playoffs-monte-carlo-simulator.git
cd nfl-playoffs-monte-carlo-simulator

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

## Disclaimer

This is an independent project not affiliated with the NFL or any official NFL service. All data is sourced from publicly available APIs.
