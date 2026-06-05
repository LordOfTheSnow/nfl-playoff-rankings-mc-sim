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

CONFERENCES: list[str] = list(NFL_TEAMS.keys())
DIVISIONS: list[str] = ["East", "North", "South", "West"]


def get_all_teams() -> list[str]:
    """Return a flat list of all 32 NFL team abbreviations."""
    return list(ALL_TEAMS)


def get_team_conference(team: str) -> str | None:
    """Return the conference (AFC or NFC) for a given team, or None if not found."""
    for conference_name, divisions in NFL_TEAMS.items():
        for division_teams in divisions.values():
            if team in division_teams:
                return conference_name
    return None


def get_team_division(team: str) -> tuple[str, str] | None:
    """Return (conference, division) for a given team, or None if not found."""
    for conference_name, divisions in NFL_TEAMS.items():
        for division_name, division_teams in divisions.items():
            if team in division_teams:
                return (conference_name, division_name)
    return None
