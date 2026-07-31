# API Reference

[← Back to README](../README.md)

All endpoints are served from a single HTTP server (default port 8080). Responses are JSON.

---

## Data Management

### `GET /api/status`

Returns the current cache status.

**Response:**

```json
{
  "season_year": 2025,
  "has_data": true,
  "completed": 240,
  "in_progress": 0,
  "scheduled": 32,
  "total_games": 272,
  "expected_total": 272,
  "weeks_fetched": 18,
  "weeks_completed": 15,
  "weeks_with_games": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
  "games_per_week": {"1": 16, "2": 16, "...": "..."},
  "cpu_count": 12
}
```

---

### `POST /api/fetch-data`

Triggers a fresh data fetch from ESPN's public API for the active season. Stores results in the local SQLite cache.

**Response:**

```json
{
  "games_fetched": 272,
  "warnings": []
}
```

---

### `POST /api/set-season`

Changes the active season year at runtime without restarting the server.

**Request body:**

```json
{ "season": 2025 }
```

| Field | Type | Constraints |
|---|---|---|
| `season` | int | 2000 - 2100 |

**Response:**

```json
{ "season_year": 2025 }
```

---

## Standings & Schedule

### `GET /api/standings`

Computes and returns current standings grouped by conference and division, including tiebreaker annotations.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `cutoff_week` | int (1-18) | all weeks | Only include games from weeks <= this value |

**Response:**

```json
{
  "conferences": {
    "AFC": {
      "East": [
        {
          "team": "Bills",
          "wins": 13,
          "losses": 3,
          "ties": 0,
          "win_percentage": 0.813,
          "games_behind": 0.0,
          "strength": 1.421,
          "division_record": "5-1-0",
          "conference_record": "9-3-0",
          "is_division_champion": true,
          "is_playoff_team": true,
          "seed": 2,
          "tiebreaker": null
        }
      ],
      "North": ["..."],
      "South": ["..."],
      "West": ["..."]
    },
    "NFC": { "...": "..." }
  },
  "bracket": {
    "afc_seeds": [
      { "team": "Chiefs", "seed": 1 },
      { "team": "Bills", "seed": 2 }
    ],
    "nfc_seeds": [
      { "team": "Lions", "seed": 1 }
    ]
  },
  "last_updated": "2025-12-25T14:30:00Z"
}
```

---

### `GET /api/schedule-grid`

Returns the league-wide schedule grid: all 32 teams with their 18-week matchup arrays.

**Response:**

```json
{
  "teams": [
    {
      "team": "Bills",
      "abbreviation": "BUF",
      "weeks": [
        {
          "opponent": "ARI",
          "home": true,
          "status": "completed",
          "team_score": 34,
          "opponent_score": 28
        },
        null,
        {
          "opponent": "MIA",
          "home": false,
          "status": "scheduled",
          "team_score": null,
          "opponent_score": null
        }
      ]
    }
  ]
}
```

Week entries are `null` for bye weeks. Status values: `"scheduled"`, `"in-progress"`, `"completed"`.

---

### `GET /api/team/{name}`

Returns a single team's full schedule with game details and current record.

**Path parameter:** team name (e.g., `Bills`, `Chiefs`, `Lions`)

**Response:**

```json
{
  "team": "Bills",
  "games": [
    {
      "week": 1,
      "opponent": "Cardinals",
      "home": true,
      "status": "completed",
      "team_score": 34,
      "opponent_score": 28,
      "result": "W"
    }
  ],
  "record": {
    "wins": 13,
    "losses": 3,
    "ties": 0,
    "win_percentage": 0.813
  }
}
```

---

### `GET /api/statistics`

Returns season-wide statistics computed from completed games.

**Response:**

```json
{
  "total_games": 240,
  "home_wins": 130,
  "away_wins": 105,
  "ties": 5,
  "home_win_pct": 54.2,
  "away_win_pct": 43.8,
  "ties_pct": 2.1,
  "avg_winner_score": 27,
  "avg_loser_score": 18,
  "overtime_games": 12,
  "overtime_pct": 5.0,
  "one_score_games": 110,
  "one_score_pct": 45.8,
  "longest_win_streak": {
    "team": "Lions",
    "streak": 11,
    "from_week": 3,
    "to_week": 13
  },
  "longest_lose_streak": {
    "team": "Titans",
    "streak": 8,
    "from_week": 2,
    "to_week": 9
  }
}
```

---

## Simulation

### `POST /api/simulate`

Runs a Monte Carlo simulation with the given parameters.

**Request body:**

```json
{
  "iterations": 10000,
  "cutoff_week": 16,
  "noise": 0.2,
  "num_workers": 4
}
```

| Field | Type | Default | Constraints |
|---|---|---|---|
| `iterations` | int | 10000 | 100 - 1,000,000 |
| `cutoff_week` | int | auto | 1 - 18 |
| `noise` | float | 0.2 | 0.0 - 1.0 |
| `num_workers` | int | CPU count | >= 1 |

**Prerequisite:** Data must be fetched first (`POST /api/fetch-data`), otherwise returns `409`.

**Response:**

```json
{
  "team_results": [
    {
      "team": "Bills",
      "conference": "AFC",
      "division": "East",
      "record": "13-3-0",
      "playoff_probability": 99.8,
      "seed_probabilities": { "1": 15.2, "2": 52.1, "3": 20.3, "4": 8.1, "5": 3.0, "6": 1.1, "7": 0.0 },
      "strength_rating": 1.4213
    }
  ],
  "top_scenarios": [
    {
      "afc_seeds": ["Chiefs", "Bills", "Ravens", "Texans", "Steelers", "Chargers", "Broncos"],
      "nfc_seeds": ["Lions", "Eagles", "Falcons", "Packers", "Vikings", "Commanders", "Buccaneers"],
      "probability": 2.34
    }
  ],
  "iterations_run": 10000,
  "cutoff_week_used": 16,
  "low_confidence": false,
  "convergence_achieved": true,
  "team_strengths": { "Bills": 1.4213, "Chiefs": 1.3891, "...": "..." },
  "fixed_games": 240,
  "simulated_games": 32
}
```

---

## Clinching & Elimination

### `GET /api/cp-clinch/{team}`

CP-SAT solver: determines whether a team has mathematically clinched or been eliminated.

**Path parameter:** team abbreviation (e.g., `DET`)

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `cutoff_week` | int (1-18) | auto | Evaluate standings at this week |
| `time_limit` | int | 30 | Solver time limit in seconds |

**Response:**

```json
{
  "team": "Lions",
  "status": "clinched",
  "clinched": true,
  "eliminated": false,
  "clinched_division": true,
  "clinched_homefield": false,
  "exhaustive": true,
  "solve_time_ms": 28,
  "num_variables": 64,
  "minimum_seed": 1,
  "magic_number": null,
  "error": null,
  "record_groups_completed": 15,
  "record_groups_total": 15
}
```

Possible `status` values: `"clinched"`, `"eliminated"`, `"alive"`, `"timeout"`

---

### `GET /api/cp-clinch-all`

Runs the CP solver for all 32 teams, grouped by conference.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `cutoff_week` | int (1-18) | auto | Evaluate standings at this week |

**Response:**

```json
{
  "cutoff_week": 16,
  "season": 2025,
  "conferences": {
    "AFC": [
      {
        "team": "Bills",
        "status": "clinched",
        "clinched_division": true,
        "clinched_homefield": false,
        "solve_time_ms": 31,
        "num_variables": 32,
        "minimum_seed": 2,
        "magic_number": null,
        "record_groups_completed": 6,
        "record_groups_total": 6
      }
    ],
    "NFC": ["..."]
  }
}
```

---

### `GET /api/clinch-estimate`

Preflight estimate for clinching scenarios — returns the problem size without running the full solver. Used for progress indicators.

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `team` | string | yes | Team name (e.g., `Bills`) |
| `cutoff_week` | int (1-18) | no | Defaults to latest completed week |

**Response:**

```json
{
  "team": "Bills",
  "relevant_games": 9,
  "method": "enumeration",
  "total_combinations": 19683,
  "estimated_time_seconds": 5.0,
  "cutoff_week": 15
}
```

---

### `POST /api/clinching-scenarios`

Computes all minimal game-outcome sets that guarantee a team a playoff spot.

**Request body:**

```json
{
  "team": "Lions",
  "cutoff_week": 15,
  "num_workers": 4,
  "enumeration_threshold": 13,
  "num_samples": 10000,
  "playoff_probability": 0.85
}
```

| Field | Type | Default | Constraints |
|---|---|---|---|
| `team` | string | — | Required, valid team name |
| `cutoff_week` | int | auto | 14 - 18 (not available before week 14) |
| `num_workers` | int | auto | 1 - CPU count |
| `enumeration_threshold` | int | 13 | 1 - 18; games above this use sampling |
| `num_samples` | int | 10000 | 100 - 100,000 |
| `playoff_probability` | float | 0.0 | MC probability for context |

**Response:**

```json
{
  "team": "Lions",
  "cutoff_week": 15,
  "record_groups": [
    {
      "wins": 3,
      "losses": 1,
      "ties": 0,
      "team_games": [
        {
          "game_id": "401671234",
          "week": 16,
          "home_team": "Lions",
          "away_team": "Bears",
          "required_winner": "Lions",
          "is_tie": false
        }
      ],
      "scenarios": [
        {
          "conditions": [
            {
              "game_id": "401671299",
              "week": 16,
              "home_team": "Vikings",
              "away_team": "Seahawks",
              "required_winner": "Seahawks",
              "is_tie": false
            }
          ],
          "num_conditions": 1
        }
      ],
      "no_path": false
    }
  ],
  "method": "enumeration",
  "exhaustive": true,
  "relevant_games_count": 9,
  "contenders": ["Lions", "Vikings", "Packers", "Bears", "Commanders"]
}
```

---

## Performance & Export

### `GET /api/solver-timings`

Returns the stored timing history from the local SQLite database.

**Response:**

```json
{
  "timings": [
    {
      "ms_per_eval": 3.45,
      "method": "enumeration",
      "relevant_games_count": 9,
      "total_evals": 19683,
      "num_workers": 12,
      "recorded_at": "2025-12-20T10:30:00"
    }
  ],
  "count": 12,
  "avg_ms_per_eval": 3.52
}
```

---

### `GET /api/export-solver-performance`

Reads existing `doc/solver-performance.md`, inserts new timing entries from the database, recalculates factors, and writes the merged file back.

**Response:**

```json
{
  "entries_added": 2,
  "output_path": "doc/solver-performance.md"
}
```

---

## Error Responses

All endpoints return errors in a consistent format:

```json
{
  "error": "Short error description",
  "details": "Longer explanation of what went wrong"
}
```

| Status | Meaning |
|---|---|
| `400` | Invalid parameters or request body |
| `404` | Endpoint not found |
| `405` | Method not allowed |
| `409` | Prerequisite not met (data not fetched yet) |
| `500` | Internal server error |
