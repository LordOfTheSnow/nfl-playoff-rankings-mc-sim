"""Application entry point for the NFL Monte Carlo Playoff Simulator.

Allows running the application as a package:
    python -m src

This delegates to the server module which handles:
- CLI argument parsing (--port, --season, --static-dir)
- Instantiation of Cache (SQLite-based persistence)
- Instantiation of DataClient (ESPN API fetcher with cache)
- HTTP server startup serving REST API and frontend static files

The Simulator and StandingsEngine are instantiated on-demand when
API endpoints are called, with cutoff_week flowing from the request
through Simulator → TeamStrengthCalculator.

Requirements: 8.1, 8.2
"""

from src.server import main

if __name__ == "__main__":
    main()
