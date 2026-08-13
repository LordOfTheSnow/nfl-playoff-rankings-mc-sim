"""NFL team structure: conferences, divisions, and team abbreviations.

Maps conferences (AFC, NFC) to divisions (East, North, South, West) to lists
of team abbreviations. Contains all 32 NFL teams.
"""

NFL_TEAMS: dict[str, dict[str, list[str]]] = {
    "AFC": {
        "East": ["Bills", "Dolphins", "Patriots", "Jets"],
        "North": ["Ravens", "Bengals", "Browns", "Steelers"],
        "South": ["Texans", "Colts", "Jaguars", "Titans"],
        "West": ["Chiefs", "Broncos", "Chargers", "Raiders"],
    },
    "NFC": {
        "East": ["Cowboys", "Eagles", "Giants", "Commanders"],
        "North": ["Bears", "Lions", "Packers", "Vikings"],
        "South": ["Falcons", "Panthers", "Saints", "Buccaneers"],
        "West": ["Cardinals", "Rams", "49ers", "Seahawks"],
    },
}


ALL_TEAMS: list[str] = [
    team
    for conference in NFL_TEAMS.values()
    for division in conference.values()
    for team in division
]

TEAM_ABBREVIATIONS: dict[str, str] = {
    "Bills": "BUF", "Dolphins": "MIA", "Patriots": "NE", "Jets": "NYJ",
    "Ravens": "BAL", "Bengals": "CIN", "Browns": "CLE", "Steelers": "PIT",
    "Texans": "HOU", "Colts": "IND", "Jaguars": "JAX", "Titans": "TEN",
    "Chiefs": "KC", "Broncos": "DEN", "Chargers": "LAC", "Raiders": "LV",
    "Cowboys": "DAL", "Eagles": "PHI", "Giants": "NYG", "Commanders": "WSH",
    "Bears": "CHI", "Lions": "DET", "Packers": "GB", "Vikings": "MIN",
    "Falcons": "ATL", "Panthers": "CAR", "Saints": "NO", "Buccaneers": "TB",
    "Cardinals": "ARI", "Rams": "LAR", "49ers": "SF", "Seahawks": "SEA",
}

CONFERENCES: list[str] = list(NFL_TEAMS.keys())
DIVISIONS: list[str] = ["East", "North", "South", "West"]

# Reverse lookup, built once at import time. compute_standings/determine_playoff_bracket
# call get_team_division/get_team_conference tens of millions of times per simulation
# run (once per team per game/tiebreaker-step comparison), so this must be O(1) rather
# than a linear scan through NFL_TEAMS.
_TEAM_LOCATIONS: dict[str, tuple[str, str]] = {
    team: (conference_name, division_name)
    for conference_name, divisions in NFL_TEAMS.items()
    for division_name, division_teams in divisions.items()
    for team in division_teams
}


def get_all_teams() -> list[str]:
    """Return a flat list of all 32 NFL team abbreviations."""
    return list(ALL_TEAMS)


def get_team_conference(team: str) -> str | None:
    """Return the conference (AFC or NFC) for a given team, or None if not found."""
    location = _TEAM_LOCATIONS.get(team)
    return location[0] if location else None


def get_team_division(team: str) -> tuple[str, str] | None:
    """Return (conference, division) for a given team, or None if not found."""
    return _TEAM_LOCATIONS.get(team)


def get_team_abbreviation(team: str) -> str | None:
    """Look up the abbreviation for a team name."""
    return TEAM_ABBREVIATIONS.get(team)
