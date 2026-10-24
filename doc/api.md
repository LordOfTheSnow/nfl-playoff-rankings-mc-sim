# API Reference

[← Back to README](../README.md)

All endpoints are served from a single HTTP server (default port 8080). Responses are JSON, except the HTML Export endpoints below, which return HTML or a ZIP file.

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
  "season_weeks": 18,
  "weeks_fetched": 18,
  "weeks_completed": 15,
  "weeks_with_games": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
  "games_per_week": {"1": 16, "2": 16, "...": "..."},
  "completed_per_week": {"1": 16, "2": 16, "...": "..."},
  "auto_cutoff_week": 15,
  "cpu_count": 12,
  "default_tie_probability": 0.0043
}
```

`season_weeks` and `expected_total` are derived from the loaded schedule's highest cached week number, not a hardcoded constant — pre-2021 seasons (16 games/17 weeks) report `season_weeks: 17`/`expected_total: 256` rather than the modern 18/272. Both are `null` if no data has been fetched yet for the active season (the shape genuinely can't be known before then).

`auto_cutoff_week` is what a request that omits `cutoff_week` would actually resolve it to — the highest week with at least one completed game (0 if none yet). This is *not* the same as `weeks_completed` (a count of weeks that are entirely finished): a week can be the auto-detected cutoff while only partially played, since fixed/simulated status is resolved per game, not per week. See "Cutoff Week" under [Algorithms](algorithms.md). `completed_per_week` (completed-game count per week, alongside `games_per_week`'s totals) lets a caller compute exactly how many games would be simulated at any candidate cutoff, including a partially-played one.

`default_tie_probability` is the tie probability `/api/simulate`/`/api/clinching-scenarios` would use if the request omits `tie_probability` — an empirical estimate (ties ÷ games pooled across every complete prior season plus the active season's own completed games through its auto-detected cutoff) once at least 2 complete prior seasons are cached, otherwise the hardcoded 0.005 default. The frontend seeds the Tie Probability slider from this value. See "Tie probability estimation" under [Algorithms](algorithms.md).

---

### `POST /api/fetch-data`

Triggers a fresh data fetch from ESPN's public API for the active season. Stores results in the local SQLite cache.

Only weeks whose cached data is stale are re-requested from ESPN: completed games never expire, a scheduled game goes stale once its kickoff time has passed (otherwise after 24 hours), and an in-progress game after 60 seconds. A week with any game cached without a `kickoff` (data from before that column existed) also counts as stale, so the first fetch after upgrading backfills it once.

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
| `cutoff_week` | int (within the loaded season's week range) | all weeks | Only include games from weeks <= this value. Out of range is treated as omitted. |

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
          "tiebreaker": null,
          "tiebreaker_detail": null
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

Teams within a division are ordered by record, then by the tiebreaker cascade among genuinely tied teams. Two teams are only tied when both win percentage **and** win-loss margin match, so early in the season, when teams have played different numbers of games, a 2-0 team ranks ahead of a 1-0 team (`games_behind` 0.5) and a 0-0 team ahead of a 0-1 team, rather than being run through the tiebreakers. This is the same rule `determine_playoff_bracket` uses to pick the division champion, so the first row of each division is always the champion. After a full season every team has played the same number of games, so it never splits a real tie.

For a genuinely tied team, `tiebreaker` is a short badge naming the deciding rule and this team's own value (e.g. `"Div 4-1-0"`, `"Common 2-0-0"`, `"H2H"`), or `"Coin toss"` if no rule in the cascade separates the whole tied group (a true, unresolved tie — the real coin toss happens outside this app). `tiebreaker_detail` is a sentence comparing this team directly against its neighbor in the standings — the team ranked just below it, or just above for the last team in a tied group — naming both teams and both of their values at the deciding step (e.g. `"Common games record: Bears 2-0-0 vs Lions 1-1-0."`). It's computed independently per pair, so two teams in a 3+-team tie never show matching numbers for a step that didn't actually distinguish them from each other. It's `null` for unresolved ("Coin toss") teams and for untied teams (where `tiebreaker` is also absent).

---

### `GET /api/schedule-grid`

Returns the league-wide schedule grid: all 32 teams with their season-length matchup arrays.

**Response:**

```json
{
  "season_weeks": 18,
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

`season_weeks` and each team's `weeks` array length are derived from the loaded schedule (17 for a pre-2021 season, 18 for 2021+). Week entries are `null` only for a true bye (no game scheduled that week). Status values: `"scheduled"`, `"in-progress"`, `"completed"`, `"postponed"`, `"cancelled"` — a postponed/cancelled game still gets its own week entry (not collapsed into `null`) so it isn't mistaken for a second bye; `team_score`/`opponent_score` are always `null` for those two statuses. Example: the 2022 season's Week 17 Bills @ Bengals game, suspended after Damar Hamlin's on-field collapse and never resumed, is reported by ESPN as `STATUS_CANCELED` and appears here with `"status": "cancelled"`.

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
      "date": "2025-09-08",
      "kickoff": "2025-09-08T00:20:00+00:00",
      "kickoff_time_valid": true,
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

`kickoff` is the game's kickoff instant in UTC (ISO 8601), straight from ESPN; `null` only for data cached before the field existed. `kickoff_time_valid` is `false` while ESPN hasn't scheduled the time yet (e.g. week 18 flex games): `kickoff` is then a placeholder at midnight Eastern that only carries the day. `date` is just the kickoff's UTC calendar date, so for night games (8:15pm ET = 00:15Z) it's already the next day — kept for compatibility; display code should use `kickoff`. The Team Detail page shows upcoming games' kickoff in the viewer's own timezone ("Thu, Oct 22 · 8:15 PM"), or the Eastern date plus "TBD" when the time isn't valid.

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
  "longest_win_streak": [
    {
      "team": "Lions",
      "streak": 11,
      "from_week": 3,
      "to_week": 13
    }
  ],
  "longest_lose_streak": [
    {
      "team": "Titans",
      "streak": 8,
      "from_week": 2,
      "to_week": 9
    }
  ],
  "margin_distribution": [
    { "label": "Tie", "count": 5, "pct": 2.1 },
    { "label": "1–3", "count": 38, "pct": 15.8 },
    { "label": "4–8", "count": 52, "pct": 21.7 },
    { "label": "9–13", "count": 47, "pct": 19.6 },
    { "label": "14–20", "count": 51, "pct": 21.3 },
    { "label": "21–27", "count": 30, "pct": 12.5 },
    { "label": "28+", "count": 17, "pct": 7.1 }
  ]
}
```

`margin_distribution` buckets every completed game by point differential (`Tie` = 0, then 1–3, 4–8, 9–13, 14–20, 21–27, 28+), each entry's `pct` relative to `total_games`.

`longest_win_streak`/`longest_lose_streak` are arrays rather than a single object because multiple teams can be tied for the longest streak (e.g. early in the season, when several teams share a 1-game streak) — each entry keeps its own `from_week`/`to_week` since tied teams don't necessarily share the same week range. Both are empty arrays when no completed games exist.

---

## Simulation

### `POST /api/simulate`

Starts a Monte Carlo simulation as a background job and returns immediately — a run can take from well under a second up to several minutes (dominated by the "impact games" ranking step; see "Cutoff Week" and the CHANGELOG for why), so it doesn't block the request. Poll `GET /api/simulate/status/{job_id}` for progress and the eventual result, and use `POST /api/simulate/cancel/{job_id}` to request a best-effort stop.

**Request body:**

```json
{
  "iterations": 10000,
  "cutoff_week": 16,
  "noise": 0.34,
  "tie_probability": 0.0043,
  "num_workers": 4
}
```

| Field | Type | Default | Constraints |
|---|---|---|---|
| `iterations` | int | 10000 | 100 - 1,000,000 |
| `cutoff_week` | int | auto | 1 - the loaded season's last week (17 pre-2021, 18 from 2021 on) |
| `noise` | float | 0.34 | 0.0 - 1.0 |
| `tie_probability` | float | empirical estimate, or 0.005 | 0.0 - 1.0; per-game tie probability. When omitted, resolved from historical data — see `default_tie_probability` on `GET /api/status` above and "Tie probability estimation" in [Algorithms](algorithms.md). |
| `num_workers` | int | CPU count | >= 1 |

**Prerequisite:** Data must be fetched first (`POST /api/fetch-data`), otherwise returns `409`. Invalid parameters (out-of-range `iterations`/`cutoff_week`/`noise`/`num_workers`/`tie_probability`) are still rejected synchronously with `400` — no job is created.

**Response** (`202 Accepted`):

```json
{ "job_id": "620725018fa640d5896fe1e1660c7222", "status": "running" }
```

---

### `GET /api/simulate/status/{job_id}`

Polls a background simulation job started by `POST /api/simulate`.

**Response while running:**

```json
{
  "job_id": "620725018fa640d5896fe1e1660c7222",
  "status": "running",
  "phase": "Ranking impact games",
  "progress_done": 15,
  "progress_total": 540
}
```

`phase` is one of `"Simulating games"` or `"Ranking impact games"` (the two internal stages of a run — see "Cutoff Week" / impact-games in [Algorithms](algorithms.md)); `progress_done`/`progress_total` count completed work units within the current phase (worker batches for the first phase, individual (team, game) impact pairs for the second) and reset across phases.

**Response once terminal** — `status` is `"completed"`, `"cancelled"`, or `"failed"`:

```json
{
  "job_id": "620725018fa640d5896fe1e1660c7222",
  "status": "completed",
  "phase": "Ranking impact games",
  "progress_done": 540,
  "progress_total": 540,
  "result": {
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
    "simulated_games": 32,
    "data_driven_pct": 61.4,
    "data_confidence": "Good",
    "next_week_matchups": [
      {
        "game_id": "401772936",
        "week": 17,
        "date": "2026-12-28",
        "home_team": "Steelers",
        "away_team": "Saints",
        "home_win_probability": 58.0,
        "away_win_probability": 41.8,
        "tie_probability": 0.2,
        "completed": false,
        "home_score": null,
        "away_score": null,
        "kickoff": "2026-12-28T01:15:00+00:00",
        "kickoff_time_valid": true
      }
    ],
    "matchups_week": 17
  }
}
```

`data_driven_pct` / `data_confidence` are a reliability indicator, not a statistical confidence level: the share (0–100, one decimal) of the league's team ratings that is based on played games rather than the league-average prior — the mean over all 32 teams of the dampening weight `n / (n + K)` (see `doc/algorithms.md`, Bayesian Dampening) — and its label (`"Very low"` < 25%, `"Low"` < 40%, `"Moderate"` < 55%, else `"Good"`). It is shown under the "Results" line on the Simulations page and in the HTML export. Note that `low_confidence` is unrelated: it only flags a run with fewer than 1000 iterations.

`next_week_matchups` covers every game in week `matchups_week`, in schedule order. `matchups_week` is `cutoff_week_used` itself while that week still has games not yet completed (e.g. the auto-detected cutoff advanced after Thursday Night Football alone), otherwise `cutoff_week_used + 1`. For each simulated game, the probabilities are a tally of which side won each simulated trial (not an extra pass, since every trial already simulates these games) — see "Next-week matchup odds" in [Algorithms](algorithms.md). Probabilities are 0-100 with one decimal and always sum to 100 for a given game; `completed` is `false` and both scores are `null`. A game in `matchups_week` that's already completed (only possible when `matchups_week == cutoff_week_used`) is a fixed input, not simulated: it has `completed: true`, its actual `home_score`/`away_score`, and all three probabilities `null`. In-progress games count as not completed and carry probabilities. `kickoff`/`kickoff_time_valid` mean the same as on `GET /api/team/{name}`; the Matchups card groups games by their kickoff's Eastern Time day. Empty when that week has no games (e.g. `cutoff_week_used` is the last week of the season) — the frontend's Export page disables the Matchups image download in that case.

`status: "failed"` carries an `error` string (same message a synchronous `400`/`500` would have used) instead of `result`. `status: "cancelled"` carries neither. A `job_id` that never existed or has aged out of the server's in-memory job registry (jobs are pruned 10 minutes after finishing; still-running jobs are never pruned) returns `404`.

---

### `POST /api/simulate/cancel/{job_id}`

Requests a best-effort stop of a running simulation job. Already-dispatched worker batches (main simulation) or in-flight impact-game calculations finish rather than being killed outright, so the job's `status` may still read `"running"` for a moment after this call returns — keep polling `GET /api/simulate/status/{job_id}` until it settles to `"cancelled"`. A no-op (still returns `200`) if the job has already reached a terminal state.

**Response:**

```json
{ "job_id": "620725018fa640d5896fe1e1660c7222", "status": "running" }
```

---

## Clinching & Elimination

### `GET /api/cp-clinch/{team}`

CP-SAT solver: determines whether a team has mathematically clinched or been eliminated.

**Path parameter:** team abbreviation (e.g., `DET`)

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `cutoff_week` | int (within the loaded season's week range) | auto | Evaluate standings at this week |
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
| `cutoff_week` | int (within the loaded season's week range) | auto | Evaluate standings at this week |

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

Preflight estimate for clinching scenarios — returns the problem size without running the full solver. Used for progress indicators. Subject to the same "4 weeks remaining" gate as `POST /api/clinching-scenarios` below — before that, returns `{"team": ..., "available": false, "reason": "..."}` instead of an estimate.

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `team` | string | yes | Team name (e.g., `Bills`) |
| `cutoff_week` | int | no | Defaults to the auto-detected cutoff — see "Cutoff Week" in [Algorithms](algorithms.md) |

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
  "playoff_probability": 0.85,
  "noise": 0.34,
  "tie_probability": 0.0043
}
```

| Field | Type | Default | Constraints |
|---|---|---|---|
| `team` | string | — | Required, valid team name |
| `cutoff_week` | int | auto | Available once 4 weeks remain before the season ends (week 14 for an 18-week season, week 13 for a 17-week one) through the loaded season's last week |
| `num_workers` | int | auto | 1 - CPU count |
| `enumeration_threshold` | int | 13 | 1 - 18; games above this use sampling |
| `num_samples` | int | 10000 | 100 - 100,000 |
| `playoff_probability` | float | 0.0 | MC probability for context |
| `noise` | float | 0.34 | 0.0 - 1.0; per-game strength noise sigma for the sampling method (ignored by enumeration). Frontend passes the same value as the main `/api/simulate` Noise control so clinching scenarios are found at a consistent rate. |
| `tie_probability` | float | empirical estimate, or 0.005 | 0.0 - 1.0; per-game tie probability for the sampling method (ignored by enumeration). When omitted, resolved the same way as `/api/simulate`'s default — see "Tie probability estimation" in [Algorithms](algorithms.md). Frontend passes the same effective value used by the main simulation for consistent results. |

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

## Wild Card Round

### `POST /api/wildcard`

Returns the Wild Card Round seeding/matchups for each conference (top 7
seeds, #1 seed's bye, and an "In the Hunt" list of teams outside the top 7
still alive), from either Actual standings or Simulated (most-likely)
seeding. See `frontend/js/wildcard.js` for the view this feeds and
`src/wildcard.py` for the assembly logic.

**Request body:**

```json
{
  "source": "actual",
  "cutoff_week": 10,
  "simulation_result": null
}
```

| Field | Type | Default | Constraints |
|---|---|---|---|
| `source` | `"actual"` \| `"simulated"` | — (required) | Which data source to seed from. |
| `cutoff_week` | int \| null | auto-detected | Actual mode only. Games up to and including this week count as real results; out-of-range or omitted falls back to auto-detection (same rule as `GET /api/standings`). Ignored for `source: "simulated"`, which uses the simulation's own `cutoff_week_used` instead. |
| `simulation_result` | object \| null | null | Required when `source: "simulated"` — the `result` object from a completed simulation job (same payload `POST /api/export/page` takes), forwarded by the client since results only live in server memory for a few minutes per job with no lookup by cutoff. Validated defensively; a malformed value is a `400`, not a silently-empty response. |

**Response:** `200 application/json`

```json
{
  "source": "actual",
  "cutoff_week": 10,
  "iterations": null,
  "conferences": {
    "AFC": [
      {
        "seed": 1,
        "team": "Chiefs",
        "conference": "AFC",
        "division": "West",
        "record": "8-2-0",
        "strength": 1.234,
        "last5": ["W", "L", "W", "W", "W"],
        "streak": { "result": "W", "length": 3 },
        "eliminated": false
      }
    ],
    "NFC": ["..."]
  }
}
```

Each conference's list always has all 16 teams, ordered by seed 1-16 (seeds
8-16 use the same conference tiebreak procedure as the playoff bracket —
`src.standings.rank_conference` — not just raw record). `iterations` is the
simulation's `iterations_run`, present only for `source: "simulated"`. Each
team entry carries `playoff_pct` (Simulated) instead of `eliminated`
(Actual). `last5` is oldest-to-newest, capped at 5 entries; `streak` is the
trailing same-result run (not capped at 5), or `null` if the team hasn't
played a game yet within the cutoff.

For Simulated mode, seeds 1-7 come from a greedy modal-seed assignment:
teams ordered by `playoff_probability` descending, each claiming its own
highest-probability seed that's still unclaimed (`src.wildcard.assign_modal_seeds`)
— this is a presentation convenience for showing one internally-consistent
bracket, not a new probability model.

**Errors:** `400` invalid JSON body, invalid `source`, or (for `source:
"simulated"`) missing/malformed `simulation_result`; `409` no cached data
for the active season (fetch data first).

---

## HTML Export

Generates standalone HTML (no server or JavaScript required to view) of the
current Standings, Statistics, Schedule Grid, Simulation, and Wild Card Round
results, in the same "Modernist" design system as the live app. Simulation
results only live in server memory for a few minutes per job (see
`POST /api/simulate` / `GET /api/simulate/status/{job_id}`), so both
endpoints take the already-fetched simulation result as part of the request
body instead of looking one up server-side — if omitted, the Simulation
section is left out of the export (this is not an error). The Wild Card
Round section always includes an Actual-standings subsection (no simulation
needed, same `cutoff_week` as the rest of the export) and additionally a
Simulated-seeding subsection whenever `simulation_result` was supplied — each
subsection is an independently collapsible `<details>` disclosure.

Every exported page (single page and every bundle page) opens with the live
app's header — the NFL logo and "NFL PLAYOFF RANKINGS SIM" brand bar
(without the interactive nav links/season selector) and the "not affiliated
with the NFL" disclaimer strip. In the bundle, the brand links to `index.html`.

### `POST /api/export/page`

Renders a single, self-contained HTML page (inline CSS) with Standings,
Statistics, Schedule Grid, Simulation (if supplied), and Wild Card Round.
Team names are plain text — this mode has no per-team pages/links, to keep
the page a manageable size.

**Request body:**

```json
{
  "simulation_result": { "...": "the result object from GET /api/simulate/status/{job_id}, or null" },
  "cutoff_week": 10
}
```

| Field | Type | Default | Constraints |
|---|---|---|---|
| `simulation_result` | object \| null | null | The `result` object from a completed simulation job. Validated defensively; a malformed value is treated the same as `null` (Simulation section omitted) rather than causing an error. |
| `cutoff_week` | int \| null | null (full season) | Applied to the Standings section, matching `GET /api/standings`'s `cutoff_week` query param, and shown as the "Week N cutoff" (vs. "Auto cutoff") title on the Simulation section's Season data card. |

**Response:** `200 text/html; charset=utf-8` — the full HTML document.

If `simulation_result` was supplied, the Simulation section also includes the same "Season data" card and "N games × M iterations = total game simulations" line shown on the live Simulations page header (from `GET /api/status`, fetched fresh at export time — not part of the request body).

**Errors:** `400` invalid JSON body; `409` no cached data for the active season (fetch data first).

### `POST /api/export/bundle`

Same request body as `POST /api/export/page`. Renders a ZIP archive containing:

- `index.html` — links to the section pages below plus a directory of all 32 teams.
- `standings.html`, `statistics.html`, `schedule-grid.html` — one page per section.
- `simulations.html` — included only when `simulation_result` was supplied.
- `wildcard.html` — Actual Standings subsection always, plus a Simulated Seeding subsection when `simulation_result` was supplied; each independently collapsible.
- `team-<slug>.html` — one per team (record, division/conference, standings row, full schedule, and simulation probabilities if available). `<slug>` is the team name lowercased (e.g. `team-chiefs.html`, `team-49ers.html`).
- `styles.css` — shared by every page above.
- `img/logos/*.png` — the NFL, AFC/NFC, and 32 team logos referenced by the pages.

Every team name anywhere in the bundle links to that team's page.

**Response:** `200 application/zip`, `Content-Disposition: attachment; filename="nfl-playoff-rankings-mc-sim-export-<season>.zip"`.

**Errors:** `400` invalid JSON body; `409` no cached data for the active season (fetch data first).

---

## Teaser Image

The Export page can download a "Biggest movers" PNG in one of three formats: landscape 1200×630 (link previews), portrait 4:5 1080×1350 (feeds), or 9:16 1080×1920 (Stories; the top ~250px is kept free of text for the platform UI, and a stylised dot plot captioned with the run's iteration count sits above the footer). Portrait files are named with a `-portrait-4x5` or `-portrait-9x16` suffix. Each shows the five teams whose playoff probability changed most since a saved baseline. The card is drawn in the browser (`frontend/js/teaser.js`) from the last simulation result and the baseline below; the server only stores and returns the baseline. The baseline is saved explicitly, one per season, so each week's deltas stay pinned to the numbers that were published.

The Export page also offers a 9:16-only "Matchups" card: one row per game in `matchups_week`, each a stacked home/away/tie probability bar between the two teams' logo and name (`renderMatchupsTeaserCanvas` in `frontend/js/teaser.js`). Already-completed games show a "FINAL" label and the actual score in place of the bar, with the winner's score in their team color and the loser's grayed out; the subtitle then notes how many games are final. Below the subtitle, the card repeats the Simulations page's simulation-quality indicator ("Data-driven ratings: N% — <label>", from the result's `data_driven_pct`/`data_confidence`), omitted for results that lack those fields, followed by a fixed one-line method note (`TEASER_MATCHUPS_METHOD_NOTE`) telling viewers without app context that the odds rest on team strength from this season's results only — no home field, weather, injuries, stats. Unlike the Movers card, this is a pure live render straight from the last simulation result's `next_week_matchups` — no baseline, no extra request — the same pattern the Wild Card bracket card uses. Each team's name/logo always use a fixed per-team color (`TEAM_COLORS`); the bar fill normally matches, but when two teams in the same matchup share a color family (e.g. two red-branded franchises), the away segment is automatically lightened so the split still reads as two distinct colors instead of one solid block — see "Next-week matchup odds" in [Algorithms](algorithms.md). The download button is disabled when `next_week_matchups` is empty (cutoff week is the last week of the season).

### `GET /api/teaser/baseline`

Returns the baseline saved for the active season.

**Response:** `200`

```json
{
  "baseline": {
    "season": 2025,
    "cutoff_week": 9,
    "saved_at": "2026-10-04T09:11:30.123456+00:00",
    "probabilities": {"Bears": 12.4, "Bengals": 3.0, "...": "..."}
  }
}
```

`baseline` is `null` when no baseline has been saved for the season. `probabilities` maps all 32 team short names to playoff probability (0–100, one decimal), as in `GET /api/simulate/status/{job_id}`'s `team_results`.

### `POST /api/teaser/baseline`

Saves the playoff probabilities of a completed simulation run as the active season's baseline, replacing any earlier one.

**Request body:**

```json
{ "simulation_result": { "cutoff_week_used": 9, "team_results": [ { "team": "Bears", "playoff_probability": 12.4 } ] } }
```

`simulation_result` is the last completed simulation result (the `result` object from `GET /api/simulate/status/{job_id}`). Only `team_results` (every team's `playoff_probability`) and `cutoff_week_used` are read.

**Response:** `200` with the saved baseline, in the same shape as the `GET` response's `baseline`.

**Errors:** `400` invalid JSON body; `400` `simulation_result` lacks a finite probability between 0 and 100 for every one of the 32 teams, or `cutoff_week_used` is not an integer.

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

## System

### `GET /api/system-info`

Returns SQLite cache database metadata (which seasons are stored and how complete each one is, plus recent ESPN fetch attempts), the server's runtime environment (CPU, Python, platform), and lifetime run counters. Backs the "Settings / Info" page.

`lifetime_counters` are persisted in the `run_counters` table: `games_simulated_total` sums the individual game outcomes rolled across every successful `POST /api/simulate` call against this database (`iterations_run × simulated_games_count` per call); `clinching_resolver_evals_total` sums `total_evals` (the number of game-outcome universes evaluated) of every successful `POST /api/clinching-scenarios` call. Both can be zeroed via `POST /api/reset-counters`.

`database.seasons[].season_weeks`/`expected_games` are derived per season from that season's own cached schedule (see `GET /api/status` above) — a pre-2021 season cached alongside a modern one reports its own 17/256 rather than sharing a single global 18/272.

`database.recent_fetches` is the 20 most recent rows from the `fetch_log` table (one row per week per fetch attempt), most recent first. `success: false` rows are ESPN fetches that failed (timeout, HTTP error, network error, or a schema error) — `games_count` is 0 for those.

`runtime.simulation_mp_method` and `runtime.clinching_resolver_mp_method` can differ: simulation always uses a fixed context (`fork` on Unix, `spawn` on Windows), while the clinching resolver uses Python's platform-default multiprocessing start method, which varies by Python version (e.g. `forkserver` became the Linux default starting in Python 3.14).

**Response:**

```json
{
  "version": "0.5.0",
  "season_year": 2025,
  "database": {
    "path": "nfl_cache.db",
    "size_bytes": 2457600,
    "seasons": [
      {
        "year": 2025,
        "games_cached": 272,
        "completed_games": 240,
        "weeks_with_data": 18,
        "season_weeks": 18,
        "expected_games": 272,
        "last_fetch_time": "2025-12-20T10:30:00+00:00"
      }
    ],
    "recent_fetches": [
      {
        "year": 2025,
        "week": 18,
        "fetched_at": "2025-12-20T10:30:00+00:00",
        "games_count": 0,
        "success": false
      },
      {
        "year": 2025,
        "week": 17,
        "fetched_at": "2025-12-20T10:29:58+00:00",
        "games_count": 16,
        "success": true
      }
    ]
  },
  "runtime": {
    "cpu_model": "12th Gen Intel(R) Core(TM) i5-1245U",
    "cpu_cores": 12,
    "python_version": "3.11.9",
    "platform": "Linux-6.8.0-x86_64-with-glibc2.39",
    "simulation_mp_method": "fork",
    "clinching_resolver_mp_method": "fork"
  },
  "lifetime_counters": {
    "games_simulated_total": 55940000,
    "clinching_resolver_evals_total": 812400
  }
}
```

---

### `POST /api/reset-counters`

Zeroes the `lifetime_counters` shown on Settings / Info (`games_simulated_total` and `clinching_resolver_evals_total`) in the `run_counters` table. No request body. Nothing else — cached game/schedule data, standings, solver timings, or fetch history — is affected.

**Response:**

```json
{
  "games_simulated_total": 0,
  "clinching_resolver_evals_total": 0
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
