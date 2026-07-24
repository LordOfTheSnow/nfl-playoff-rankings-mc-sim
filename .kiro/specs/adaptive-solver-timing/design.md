# Design: Adaptive Solver Time Estimation

## Context

The clinching solver (`src/clinching.py`) currently uses a synthetic benchmark to estimate runtime for the `/api/clinch-estimate` endpoint. This benchmark runs 100 artificial iterations of `_check_universe()` and caches the result for 24 hours. The estimate is often inaccurate because:

1. The benchmark uses a fixed "Bills" team and arbitrary game data, not real workloads.
2. Hardware performance varies with CPU load, thermal throttling, and OS scheduling.
3. The benchmark cannot account for differences between enumeration and sampling methods.

This design replaces the synthetic benchmark with a rolling average of actual solver performance measurements, stored persistently in SQLite. The existing `run_benchmark()` function serves only as a cold-start seed when no historical data exists.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Server Layer                                   │
│  _handle_get_clinch_estimate() ──► estimate_clinching(cache=)           │
│  _handle_post_clinching_scenarios():                                    │
│    1. start_time = time.perf_counter()                                  │
│    2. result = compute_clinching_scenarios(team, games, cutoff_week, …) │
│    3. try: send response                                                │
│    4. except BrokenPipeError: return (user cancelled, NO timing stored) │
│    5. elapsed = perf_counter() - start_time                             │
│    6. cache.store_solver_timing(ms_per_eval, method, …)                 │
└─────────────────┬───────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────┐   ┌──────────────────────────────┐
│     Clinching Module        │   │       Cache Module            │
│  get_ms_per_eval(cache=)    │   │  store_solver_timing()        │
│  estimate_clinching(cache=) │   │  get_solver_timings()         │
│  compute_clinching_scenarios│   │  _create_tables() [schema]    │
│  (no cache param — timing   │   └──────────────────────────────┘
│   is server's concern)      │               │
└─────────────────────────────┘               ▼
                                  ┌──────────────────────┐
                                  │   solver_timing table │
                                  │   (nfl_cache.db)      │
                                  └──────────────────────┘
```

## Key Design Decision: Server-Layer Timing Storage

Timing measurements are stored at the **server layer** (`_handle_post_clinching_scenarios()`), not inside `compute_clinching_scenarios()`. This enables:

1. **Cancellation detection**: The server can detect BrokenPipeError when writing the response (caused by client AbortController abort). Cancelled runs must not store timing data because they may represent incomplete or interrupted computations.
2. **Separation of concerns**: The solver function computes scenarios; the server manages the request lifecycle and persistence side effects.
3. **Accurate wall-clock measurement**: The timer spans from before the solver call to after successful delivery, capturing the full request handling time.

The trade-off is that `compute_clinching_scenarios()` must expose enough metadata in its result (method, total_evals derivable from the result fields) for the server to compute ms_per_eval externally.

## Components

### 1. Cache Module (`src/cache.py`)

**New table**: `solver_timing`

```sql
CREATE TABLE IF NOT EXISTS solver_timing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ms_per_eval REAL NOT NULL,
    method TEXT NOT NULL,
    relevant_games_count INTEGER NOT NULL,
    total_evals INTEGER NOT NULL,
    recorded_at TEXT NOT NULL
);
```

**New methods** on the `Cache` class:

#### `store_solver_timing()`

Inserts a measurement record and prunes old entries beyond the rolling window of 50.

```python
def store_solver_timing(
    self,
    ms_per_eval: float,
    method: str,
    relevant_games_count: int,
    total_evals: int,
) -> None:
    """Store a solver timing measurement and prune old records.

    Inserts the measurement with the current UTC timestamp, then
    deletes all records beyond the 50 most recent.

    Args:
        ms_per_eval: Milliseconds per evaluation (wall-clock / total_evals * 1000).
        method: "enumeration" or "sampling".
        relevant_games_count: Number of relevant other games in the analysis.
        total_evals: Total number of universe evaluations performed.
    """
    now = datetime.now(UTC).isoformat()
    self._conn.execute(
        """INSERT INTO solver_timing
           (ms_per_eval, method, relevant_games_count, total_evals, recorded_at)
           VALUES (?, ?, ?, ?, ?)""",
        (ms_per_eval, method, relevant_games_count, total_evals, now),
    )
    # Prune: keep only the 50 most recent records
    self._conn.execute(
        """DELETE FROM solver_timing WHERE id NOT IN (
            SELECT id FROM solver_timing ORDER BY recorded_at DESC LIMIT 50
        )"""
    )
    self._conn.commit()
```

#### `get_solver_timings()`

Retrieves the most recent 50 records as a list of dictionaries.

```python
def get_solver_timings(self, limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve the most recent solver timing measurements.

    Args:
        limit: Maximum number of records to return (default 50).

    Returns:
        List of dicts with keys: ms_per_eval, method,
        relevant_games_count, total_evals, recorded_at.
        Ordered by recorded_at descending.
    """
    rows = self._conn.execute(
        "SELECT ms_per_eval, method, relevant_games_count, total_evals, recorded_at "
        "FROM solver_timing ORDER BY recorded_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "ms_per_eval": row["ms_per_eval"],
            "method": row["method"],
            "relevant_games_count": row["relevant_games_count"],
            "total_evals": row["total_evals"],
            "recorded_at": row["recorded_at"],
        }
        for row in rows
    ]
```

### 2. Clinching Module (`src/clinching.py`)

#### Modified `get_ms_per_eval()`

Adds an optional `cache` parameter. When a cache with historical data is available, returns the arithmetic mean of stored ms_per_eval values. Falls back to the existing benchmark/global behavior when cache is None or empty.

```python
def get_ms_per_eval(
    all_games: list[Game] | None = None,
    cache: Cache | None = None,
) -> float:
    """Get ms/eval from historical data or fall back to benchmark.

    Priority:
    1. If cache has timing records → arithmetic mean of rolling window
    2. If all_games provided → run_benchmark(all_games)
    3. Module-level cached benchmark (existing global)
    4. Conservative default: 2.0 ms

    Args:
        all_games: Season games (used for benchmark fallback).
        cache: Optional Cache instance for historical timing data.

    Returns:
        Estimated milliseconds per clinching evaluation.
    """
    global _benchmark_ms_per_eval

    if cache is not None:
        timings = cache.get_solver_timings()
        if timings:
            total = sum(t["ms_per_eval"] for t in timings)
            return total / len(timings)

    # Fallback: existing behavior
    if _benchmark_ms_per_eval is not None:
        return _benchmark_ms_per_eval
    if all_games:
        return run_benchmark(all_games)
    return 2.0
```

#### Modified `estimate_clinching()`

Adds an optional `cache` parameter and passes it to `get_ms_per_eval()`.

```python
def estimate_clinching(
    team: str,
    all_games: list[Game],
    cutoff_week: int,
    cache: Cache | None = None,
) -> dict[str, Any]:
    """Lightweight preflight estimate for the clinching solver.

    Args:
        team: Team name.
        all_games: All season games.
        cutoff_week: Week number cutoff.
        cache: Optional Cache instance for adaptive timing.

    Returns:
        Dict with estimation data including estimated_seconds.
    """
    # ... existing validation logic unchanged ...

    ms_per_eval = get_ms_per_eval(all_games, cache=cache)

    # ... rest of calculation unchanged ...
```

#### `compute_clinching_scenarios()` — NO cache parameter

The function signature does NOT include a `cache` parameter. Timing storage is the server layer's responsibility. The function's result (ClinchingResult) already contains enough information for the server to derive timing metadata:

- **method**: Determined by whether the solver used enumeration or sampling (derivable from the result's `method` field or from the solver's decision logic based on the number of other games vs the enumeration threshold).
- **total_evals**: Derivable from `n_team_combos * (3 ** len(other_games))` for enumeration, or `n_team_combos * num_samples` for sampling. The server can compute this from the result metadata or pass-through values.

To support external timing computation, `ClinchingResult` exposes:
- `method` (str): "enumeration" or "sampling"
- `total_evals` (int): Total universe evaluations performed
- `relevant_games_count` (int): Number of relevant other games

These fields are already present or easily added to ClinchingResult since it is a dataclass built during the solver run.

```python
def compute_clinching_scenarios(
    team: str,
    all_games: list[Game],
    cutoff_week: int,
    num_workers: int | None = None,
    enumeration_threshold: int | None = None,
    num_samples: int | None = None,
) -> ClinchingResult:
    """Compute all clinching scenarios for a team.

    Args:
        team: Team name to analyze.
        all_games: All season games.
        cutoff_week: Games up to this week are fixed (completed).
        num_workers: Number of worker processes (None = auto-detect).
        enumeration_threshold: Override for ENUMERATION_THRESHOLD.
        num_samples: Override for MC_SAMPLES.

    Returns:
        ClinchingResult with all scenarios grouped by team record,
        including method, total_evals, and relevant_games_count
        metadata for external timing computation.
    """
    # ... existing solver logic ...
    # Result includes method, total_evals, relevant_games_count fields
```

### 3. Server Module (`src/server.py`)

#### Modified `_handle_get_clinch_estimate()`

Removes the explicit `run_benchmark()` call and passes the server's cache to `estimate_clinching()`.

```python
def _handle_get_clinch_estimate(self) -> None:
    # ... existing parameter parsing ...

    from src.clinching import estimate_clinching
    # No more: run_benchmark(games)
    result = estimate_clinching(team, games, cutoff_week, cache=server.cache)
    result["cutoff_week"] = cutoff_week
    self._send_json_response(200, result)
```

#### Modified `_handle_post_clinching_scenarios()`

Implements the full timing lifecycle: measure wall-clock time, call the solver, attempt response delivery, and store timing only on success.

```python
def _handle_post_clinching_scenarios(self) -> None:
    """Handle POST /api/clinching-scenarios — compute clinching scenarios for a team."""
    server: NFLSimulatorServer = self.server  # type: ignore[assignment]

    # ... existing parameter parsing and validation ...

    try:
        from src.clinching import compute_clinching_scenarios
        # ... existing parameter extraction (enum_threshold, num_samples, num_workers) ...

        start_time = time.perf_counter()

        result = compute_clinching_scenarios(
            team, games, cutoff_week,
            num_workers=num_workers,
            enumeration_threshold=enum_threshold,
            num_samples=num_samples,
        )

        if result.error:
            self._send_error_response(400, result.error, "")
            return

        # Serialize result
        response = self._serialize_clinching_result(result)
        response["cutoff_week"] = cutoff_week

        try:
            self._send_json_response(200, response)
        except BrokenPipeError:
            # User cancelled (AbortController abort) — do NOT store timing
            return

        # Successfully delivered response → store timing
        elapsed_seconds = time.perf_counter() - start_time
        total_evals = result.total_evals
        if total_evals > 0:
            ms_per_eval = (elapsed_seconds * 1000) / total_evals
            server.cache.store_solver_timing(
                ms_per_eval=ms_per_eval,
                method=result.method,
                relevant_games_count=result.relevant_games_count,
                total_evals=total_evals,
            )

    except Exception as e:
        logger.exception("Error computing clinching scenarios")
        self._send_error_response(500, "Clinching analysis error", str(e))
```

### 4. Timing History UI (Frontend)

#### Server Endpoint: `GET /api/solver-timings`

Returns the stored timing records for display in the frontend.

```python
def _handle_get_solver_timings(self) -> None:
    """Handle GET /api/solver-timings — return stored timing history."""
    server: NFLSimulatorServer = self.server  # type: ignore[assignment]
    timings = server.cache.get_solver_timings()
    count = len(timings)
    avg_ms_per_eval = (
        sum(t["ms_per_eval"] for t in timings) / count if count > 0 else 0.0
    )
    self._send_json_response(200, {
        "timings": timings,
        "count": count,
        "avg_ms_per_eval": round(avg_ms_per_eval, 4),
    })
```

Response schema:
```json
{
  "timings": [
    {
      "ms_per_eval": 1.23,
      "method": "enumeration",
      "relevant_games_count": 7,
      "total_evals": 131072,
      "recorded_at": "2025-01-15T10:30:00+00:00"
    }
  ],
  "count": 12,
  "avg_ms_per_eval": 1.45
}
```

Returns an empty array with count 0 and avg_ms_per_eval 0.0 when no data exists.

#### Frontend: API Function (`frontend/js/api.js`)

```javascript
/**
 * Get solver timing history.
 * GET /api/solver-timings
 *
 * @returns {Promise<{timings: Object[], count: number, avg_ms_per_eval: number}>}
 */
function solverTimings() {
  return request("/api/solver-timings");
}
```

Exposed via the `API` module's return object.

#### Frontend: Timing History Button and Modal (`frontend/js/simulation.js`)

A small "Timing History" button (`btn-sm btn-outline-info`) is placed inside the clinching section's `<div class="d-flex gap-2 flex-wrap align-items-center">` container, next to the "Clinching Scenarios" button.

On click, the button:
1. Calls `API.solverTimings()` to fetch data
2. Renders a Bootstrap modal with:
   - **Title**: "Solver Timing History"
   - **Explanatory paragraph**: "These measurements are collected after each solver run and used to calibrate time estimates. The system keeps the last 50 measurements."
   - **Summary line**: Shows count and average ms/eval (e.g., "12 measurements, avg 1.45 ms/eval")
   - **Scrollable table** (max-height: 300px, `overflow-y: auto`) with columns: ms/eval, Method, Games, Evaluations, Recorded At
   - **Empty state**: If count is 0, show a Bootstrap info alert: "No timing data collected yet. Run the clinching solver to start building calibration data."
3. Shows the modal via Bootstrap's `Modal` API

The modal markup is appended to the DOM once on first use and reused on subsequent clicks. The table body is re-rendered on each open to reflect the latest data.

```html
<!-- Modal structure (appended once) -->
<div class="modal fade" id="timingHistoryModal" tabindex="-1" aria-labelledby="timingHistoryModalLabel" aria-hidden="true">
  <div class="modal-dialog modal-lg">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="timingHistoryModalLabel">Solver Timing History</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body" id="timingHistoryBody">
        <!-- Populated dynamically -->
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
      </div>
    </div>
  </div>
</div>
```

## Data Model

### solver_timing Table

| Column | Type | Constraint | Description |
|--------|------|-----------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique record identifier |
| ms_per_eval | REAL | NOT NULL | Wall-clock ms per evaluation |
| method | TEXT | NOT NULL | "enumeration" or "sampling" |
| relevant_games_count | INTEGER | NOT NULL | Number of relevant other games |
| total_evals | INTEGER | NOT NULL | Total universe evaluations |
| recorded_at | TEXT | NOT NULL | UTC ISO-8601 timestamp |

### ClinchingResult Metadata Fields

The `ClinchingResult` dataclass exposes fields needed for external timing computation:

| Field | Type | Description |
|-------|------|-------------|
| method | str | "enumeration" or "sampling" |
| total_evals | int | Total universe evaluations performed |
| relevant_games_count | int | Number of relevant other games analyzed |

### Rolling Window Semantics

- Window size: 50 records (most recent by `recorded_at`)
- Pruning: On each `store_solver_timing()` call, records beyond the window are deleted
- The window includes all methods — no partitioning. This provides a hardware-level performance estimate that accounts for varying workloads.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `compute_clinching_scenarios()` returns error (e.g., week < 14) | No timing record stored; error response sent immediately |
| `total_evals` is 0 (edge case: no games to evaluate) | No timing record stored (division by zero guard) |
| BrokenPipeError on response write (user cancelled) | No timing record stored; handler returns immediately |
| Cache is None (backward compat for estimation) | `get_ms_per_eval()` uses existing benchmark/global behavior |
| SQLite write fails during store_solver_timing | Exception propagates; solver result already delivered to client |
| Empty timing table + no games data | `get_ms_per_eval()` returns conservative default 2.0 ms |

## Backward Compatibility

- `get_ms_per_eval()` and `estimate_clinching()` have optional `cache` parameters with `None` defaults
- `compute_clinching_scenarios()` signature is unchanged (no new parameters)
- Existing callers of all functions continue to work without modification
- The module-level globals (`_benchmark_ms_per_eval`, `_benchmark_timestamp`) remain for the fallback path
- `run_benchmark()` remains available but is no longer called by the server's estimate handler

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Store/Retrieve Round Trip

*For any* valid solver timing measurement (positive ms_per_eval, method in {"enumeration", "sampling"}, positive relevant_games_count, positive total_evals), storing it via `store_solver_timing()` and then retrieving via `get_solver_timings()` SHALL produce a record with matching ms_per_eval, method, relevant_games_count, total_evals values and a valid ISO-8601 recorded_at timestamp.

**Validates: Requirements 1.3, 3.3**

### Property 2: Rolling Window Size Invariant

*For any* sequence of N store operations (N >= 0), `get_solver_timings()` SHALL return exactly min(N, 50) records, and those records SHALL be the min(N, 50) most recently stored (ordered by recorded_at descending). Additionally, the underlying table SHALL never contain more than 50 records after any `store_solver_timing()` call.

**Validates: Requirements 3.1, 3.2, 7.1**

### Property 3: Adaptive Mean Estimation

*For any* non-empty set of solver timing records in the cache (up to 50), calling `get_ms_per_eval(cache=cache)` SHALL return a value equal to the arithmetic mean of the ms_per_eval values in those records (within floating-point tolerance).

**Validates: Requirements 4.1, 5.2**

### Property 4: Cache-None Backward Compatibility

*For any* call to `get_ms_per_eval(cache=None)` when the module-level `_benchmark_ms_per_eval` global is set to a positive value, the function SHALL return that global value without querying any database.

**Validates: Requirements 5.3**

### Property 5: Cancellation Safety

*For any* solver run where the client disconnects during response delivery (BrokenPipeError raised by `_send_json_response()`), the Scenarios_Endpoint SHALL NOT call `store_solver_timing()`. The timing store SHALL contain the same number of records before and after the cancelled request.

**Validates: Requirements 2.2, 6.2**
