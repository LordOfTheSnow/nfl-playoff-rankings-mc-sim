# NFL Playoffs Monte Carlo Simulator

A web application that predicts NFL playoff outcomes using Monte Carlo simulation. It fetches real game data from ESPN's public API, computes strength-of-schedule-weighted team ratings, simulates remaining games, applies official NFL tiebreaker rules, and presents probability distributions through an interactive browser UI.

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
python -m src --season 2025 --port 9090
```

Then open http://localhost:8080 in your browser.

1. Go to **Simulate** and click **Fetch Data** to pull game data from ESPN
2. View current standings on the **Standings** page
3. Configure simulation parameters and click **Run Simulation**
4. View results on the **Results** page

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Disclaimer

This is an independent project not affiliated with the NFL or any official NFL service. All data is sourced from publicly available APIs.
