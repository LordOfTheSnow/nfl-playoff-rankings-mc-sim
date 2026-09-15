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
    "simulated_games": 32
  }
}
```

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

## HTML Export

Generates standalone HTML (no server or JavaScript required to view) of the
current Standings, Statistics, Schedule Grid, and Simulation results, in the
same "Modernist" design system as the live app. Simulation results only live
in server memory for a few minutes per job (see `POST /api/simulate` /
`GET /api/simulate/status/{job_id}`), so both endpoints take the
already-fetched simulation result as part of the request body instead of
looking one up server-side — if omitted, the Simulation section is left out
of the export (this is not an error).

### `POST /api/export/page`

Renders a single, self-contained HTML page (inline CSS) with Standings,
Statistics, Schedule Grid, and Simulation (if supplied). Team names are
plain text — this mode has no per-team pages/links, to keep the page a
manageable size.

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
- `team-<slug>.html` — one per team (record, division/conference, standings row, full schedule, and simulation probabilities if available). `<slug>` is the team name lowercased (e.g. `team-chiefs.html`, `team-49ers.html`).
- `styles.css` — shared by every page above.

Every team name anywhere in the bundle links to that team's page.

**Response:** `200 application/zip`, `Content-Disposition: attachment; filename="nfl-export-<season>.zip"`.

**Errors:** `400` invalid JSON body; `409` no cached data for the active season (fetch data first).

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
