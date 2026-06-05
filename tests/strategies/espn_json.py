"""Hypothesis strategies for generating valid ESPN scoreboard JSON responses."""

from hypothesis import strategies as st

from src.nfl_teams import ALL_TEAMS


# ESPN status type name mapping
ESPN_STATUS_NAMES = [
    "STATUS_SCHEDULED",
    "STATUS_IN_PROGRESS",
    "STATUS_FINAL",
    "STATUS_POSTPONED",
    "STATUS_CANCELED",
]

espn_status_name = st.sampled_from(ESPN_STATUS_NAMES)

# Strategy for generating a valid ESPN game ID (numeric string)
espn_game_id = st.integers(min_value=100000000, max_value=999999999).map(str)

# Strategy for generating an ESPN-format date (ISO 8601 with time)
espn_date = st.builds(
    lambda y, m, d: f"{y}-{m:02d}-{d:02d}T13:00Z",
    st.integers(min_value=2020, max_value=2030),
    st.integers(min_value=9, max_value=12),
    st.integers(min_value=1, max_value=28),
)

# Strategy for generating a valid score as a string (ESPN returns scores as strings)
espn_score = st.integers(min_value=0, max_value=70).map(str)

# Strategy for generating a display clock
espn_display_clock = st.builds(
    lambda m, s: f"{m}:{s:02d}",
    st.integers(min_value=0, max_value=15),
    st.integers(min_value=0, max_value=59),
)

# Strategy for generating a quarter/period number
espn_period = st.integers(min_value=1, max_value=5)

# Strategy for generating a week number
espn_week_number = st.integers(min_value=1, max_value=18)


@st.composite
def espn_competitor(draw: st.DrawFn, home_away: str, team: str | None = None) -> dict:
    """Generate a single ESPN competitor entry.

    Args:
        home_away: Either "home" or "away".
        team: Team name to use. If None, randomly selected.
    """
    team_name = team if team is not None else draw(st.sampled_from(ALL_TEAMS))
    return {
        "homeAway": home_away,
        "team": {
            "displayName": team_name,
            "abbreviation": team_name[:3].upper(),
        },
        "score": draw(espn_score),
    }


@st.composite
def espn_event(
    draw: st.DrawFn,
    status_name: str | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
) -> dict:
    """Generate a single ESPN event (game) entry.

    Args:
        status_name: ESPN status type name. If None, randomly chosen.
        home_team: Home team name. If None, randomly chosen.
        away_team: Away team name. If None, randomly chosen.
    """
    chosen_status = status_name if status_name is not None else draw(espn_status_name)

    # Ensure home and away teams are different
    if home_team is None:
        home_team = draw(st.sampled_from(ALL_TEAMS))
    if away_team is None:
        away_team = draw(
            st.sampled_from([t for t in ALL_TEAMS if t != home_team])
        )

    home_competitor = draw(espn_competitor(home_away="home", team=home_team))
    away_competitor = draw(espn_competitor(home_away="away", team=away_team))

    # Build status object
    status: dict = {
        "type": {
            "name": chosen_status,
            "completed": chosen_status == "STATUS_FINAL",
        },
    }

    # Add period and clock for in-progress games
    if chosen_status == "STATUS_IN_PROGRESS":
        status["period"] = draw(espn_period)
        status["displayClock"] = draw(espn_display_clock)
    else:
        status["period"] = 0
        status["displayClock"] = "0:00"

    return {
        "id": draw(espn_game_id),
        "date": draw(espn_date),
        "week": {"number": draw(espn_week_number)},
        "status": status,
        "competitions": [
            {
                "competitors": [home_competitor, away_competitor],
            }
        ],
    }


@st.composite
def espn_scoreboard_response(
    draw: st.DrawFn,
    min_events: int = 1,
    max_events: int = 16,
    status_name: str | None = None,
) -> dict:
    """Generate a complete ESPN scoreboard API response.

    Args:
        min_events: Minimum number of game events to include.
        max_events: Maximum number of game events to include.
        status_name: If provided, all events will have this status.
    """
    num_events = draw(st.integers(min_value=min_events, max_value=max_events))
    events = [draw(espn_event(status_name=status_name)) for _ in range(num_events)]

    return {
        "events": events,
        "leagues": [
            {
                "id": "28",
                "name": "National Football League",
                "abbreviation": "NFL",
            }
        ],
        "season": {
            "type": 2,
            "year": draw(st.integers(min_value=2020, max_value=2030)),
        },
    }


@st.composite
def espn_event_missing_field(draw: st.DrawFn, missing_field: str | None = None) -> dict:
    """Generate an ESPN event with a required field removed.

    Args:
        missing_field: The field to remove. If None, randomly chosen from required fields.
    """
    event = draw(espn_event())

    required_fields = ["id", "date", "status", "competitions", "week"]
    field_to_remove = missing_field if missing_field is not None else draw(
        st.sampled_from(required_fields)
    )

    if field_to_remove in event:
        del event[field_to_remove]
    elif field_to_remove == "team_name":
        # Remove team displayName from home competitor
        event["competitions"][0]["competitors"][0]["team"].pop("displayName", None)
    elif field_to_remove == "score":
        # Remove score from home competitor
        event["competitions"][0]["competitors"][0].pop("score", None)

    return event


@st.composite
def espn_scoreboard_with_missing_fields(draw: st.DrawFn) -> dict:
    """Generate an ESPN scoreboard response where one event has a missing required field."""
    response = draw(espn_scoreboard_response(min_events=1, max_events=5))

    # Pick one event and remove a required field
    if response["events"]:
        idx = draw(st.integers(min_value=0, max_value=len(response["events"]) - 1))
        response["events"][idx] = draw(espn_event_missing_field())

    return response
