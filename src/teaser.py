"""Teaser image support: extracting the baseline probabilities to save.

The teaser ("Movers") card compares each team's playoff probability against
a baseline saved from an earlier simulation run. The baseline is taken from
the simulation result the client already holds (window._simulationResults),
so this module only validates that payload and pulls out the numbers. The
rendering and the week-over-week diff live in frontend/js/teaser.js.
"""

from __future__ import annotations

import math
from typing import Any

from src.nfl_teams import ALL_TEAMS


def extract_baseline_probabilities(simulation_result: Any) -> dict[str, float] | None:
    """Return {team: playoff_probability (0-100)} for every team, or None.

    Returns None unless the payload lists a finite probability for every one
    of the 32 teams, so a partial or hand-edited result can never be saved as
    a baseline and silently produce a misleading teaser later.
    """
    if not isinstance(simulation_result, dict):
        return None
    team_results = simulation_result.get("team_results")
    if not isinstance(team_results, list):
        return None

    probabilities: dict[str, float] = {}
    for entry in team_results:
        if not isinstance(entry, dict):
            return None
        team = entry.get("team")
        probability = entry.get("playoff_probability")
        if team not in ALL_TEAMS or isinstance(probability, bool):
            return None
        if not isinstance(probability, (int, float)) or not math.isfinite(probability):
            return None
        if not 0 <= probability <= 100:
            return None
        probabilities[team] = float(probability)

    if set(probabilities) != set(ALL_TEAMS):
        return None
    return probabilities
