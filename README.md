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

When viewing simulation results, clicking a team with < 75% playoff probability shows a "Playoff Path" — the combination of game outcomes most commonly associated with that team making the playoffs.

- **Team's own games** (highlighted) appear first — these are typically essential wins
- **Other conference games** show which competitors need to lose
- **Confidence %** indicates how often that outcome appeared across qualifying trials (higher = more critical)

Note: This is a statistical analysis, not a deterministic "checklist." For very low-probability teams (< 5%), the path is based on few qualifying trials and may be noisy. More simulation iterations produce more reliable paths.

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Disclaimer

This is an independent project not affiliated with the NFL or any official NFL service. All data is sourced from publicly available APIs.
