# Implementation Plan: Adaptive Solver Time Estimation

## Overview

Replace the synthetic benchmark approach for clinching solver runtime estimation with a rolling average of actual solver performance measurements stored in SQLite. The implementation adds a `solver_timing` table to the cache, records measurements in the server handler after successful response delivery, and uses the historical average for time estimates. Timing is stored at the server layer to enable cancellation detection via BrokenPipeError — cancelled runs do not store timing data. All new parameters on estimation functions are optional to maintain backward compatibility.

## Tasks

- [x] 1. Write test skeletons for cache and clinching timing logic
  - [x] 1.1 Create test file for solver timing storage (`tests/test_solver_timing.py`)
    - Write test functions (initially failing) covering:
      - `test_store_and_retrieve_single_timing` — store one record, retrieve it, verify fields match
      - `test_rolling_window_prunes_beyond_50` — store 55 records, verify only 50 retained
      - `test_get_solver_timings_returns_most_recent_first` — verify descending order by recorded_at
      - `test_get_solver_timings_empty_table` — verify empty list returned when no data exists
      - `test_store_solver_timing_records_utc_timestamp` — verify ISO-8601 UTC timestamp
    - Use an in-memory SQLite cache (`:memory:`) for isolation
    - _Requirements: 1.1, 1.2, 1.3, 3.1, 3.2, 3.3, 7.1_
    - **Accept**: `pytest tests/test_solver_timing.py` runs — tests exist and fail with `AttributeError` or `sqlite3.OperationalError` (methods/table not yet implemented)
    - **Verify**: `python3 -m pytest tests/test_solver_timing.py --co -q` lists 5 test items

  - [x] 1.2 Create test file for adaptive ms_per_eval estimation (`tests/test_adaptive_estimation.py`)
    - Write test functions covering:
      - `test_get_ms_per_eval_with_cache_data` — returns arithmetic mean of stored timings
      - `test_get_ms_per_eval_empty_cache_falls_back_to_global` — returns module-level global when cache is empty
      - `test_get_ms_per_eval_cache_none_uses_global` — backward compat: cache=None returns global
      - `test_get_ms_per_eval_no_cache_no_global_returns_default` — returns 2.0 ms as conservative default
      - `test_estimate_clinching_passes_cache_through` — verify cache parameter reaches get_ms_per_eval
    - Use mocking/patching for module-level globals and benchmark fallback
    - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4_
    - **Accept**: `pytest tests/test_adaptive_estimation.py` runs — tests exist and fail (functions don't accept `cache` parameter yet)
    - **Verify**: `python3 -m pytest tests/test_adaptive_estimation.py --co -q` lists 5 test items

  - [x] 1.3 Create test file for server-layer timing integration (`tests/test_server_timing.py`)
    - Write test functions covering:
      - `test_scenarios_endpoint_stores_timing_after_success` — verify timing stored after successful response
      - `test_scenarios_endpoint_skips_timing_on_broken_pipe` — mock BrokenPipeError on send, verify no timing stored
      - `test_scenarios_endpoint_skips_timing_on_error_result` — verify no timing stored when solver returns error
      - `test_scenarios_endpoint_skips_timing_on_zero_evals` — verify no timing stored when total_evals is 0
    - Use mocking for compute_clinching_scenarios, _send_json_response, and cache.store_solver_timing
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 6.2_
    - **Accept**: `pytest tests/test_server_timing.py` runs — tests exist and fail (server handler not yet modified)
    - **Verify**: `python3 -m pytest tests/test_server_timing.py --co -q` lists 4 test items

- [x] 2. Implement cache layer changes
  - [x] 2.1 Add `solver_timing` table to `Cache._create_tables()` in `src/cache.py`
    - Add the CREATE TABLE IF NOT EXISTS statement for `solver_timing` with columns: id, ms_per_eval, method, relevant_games_count, total_evals, recorded_at
    - _Requirements: 1.1, 1.2_
    - **Accept**: Cache initialization creates the `solver_timing` table without errors
    - **Verify**: `python3 -c "from src.cache import Cache; c = Cache(':memory:'); print(c._conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='solver_timing'\").fetchone()[0])"`

  - [x] 2.2 Add `store_solver_timing()` method to `Cache` class in `src/cache.py`
    - Insert a record with current UTC timestamp
    - Prune records beyond the 50 most recent after each insert
    - Parameters: ms_per_eval (float), method (str), relevant_games_count (int), total_evals (int)
    - _Requirements: 1.3, 7.1_
    - **Accept**: Storing 55 records results in exactly 50 retained in the table
    - **Verify**: `python3 -m pytest tests/test_solver_timing.py::test_store_and_retrieve_single_timing tests/test_solver_timing.py::test_rolling_window_prunes_beyond_50 -v`

  - [x] 2.3 Add `get_solver_timings()` method to `Cache` class in `src/cache.py`
    - Return up to `limit` (default 50) most recent records ordered by recorded_at DESC
    - Each record returned as a dict with keys: ms_per_eval, method, relevant_games_count, total_evals, recorded_at
    - _Requirements: 3.1, 3.2, 3.3_
    - **Accept**: `pytest tests/test_solver_timing.py` — all 5 tests pass
    - **Verify**: `python3 -m pytest tests/test_solver_timing.py -v`

- [x] 3. Checkpoint - Verify cache layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement clinching module changes
  - [x] 4.1 Modify `get_ms_per_eval()` in `src/clinching.py` — add optional `cache` parameter
    - Add `cache: Cache | None = None` parameter
    - When cache is not None: query `cache.get_solver_timings()`, return arithmetic mean if records exist
    - Fall back to existing behavior (module-level global → benchmark → 2.0 ms default)
    - Import Cache type under TYPE_CHECKING to avoid circular imports
    - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2, 5.3_
    - **Accept**: `pytest tests/test_adaptive_estimation.py` — all 5 tests pass
    - **Verify**: `python3 -m pytest tests/test_adaptive_estimation.py -v`

  - [x] 4.2 Modify `estimate_clinching()` in `src/clinching.py` — add optional `cache` parameter
    - Add `cache: Cache | None = None` parameter
    - Pass `cache` through to `get_ms_per_eval(all_games, cache=cache)`
    - _Requirements: 5.4_
    - **Accept**: `estimate_clinching()` accepts `cache` kwarg and forwards it
    - **Verify**: `python3 -m pytest tests/test_adaptive_estimation.py::test_estimate_clinching_passes_cache_through -v`

  - [x] 4.3 Ensure `ClinchingResult` exposes timing metadata fields
    - Verify/add `method` (str), `total_evals` (int), and `relevant_games_count` (int) fields to ClinchingResult dataclass
    - These fields are populated during the solver run so the server can compute ms_per_eval externally
    - `compute_clinching_scenarios()` does NOT accept a `cache` parameter — timing is the server's responsibility
    - _Requirements: 2.4, 5.5_
    - **Accept**: `ClinchingResult` instances have `method`, `total_evals`, and `relevant_games_count` attributes accessible after solver completion
    - **Verify**: `python3 -c "from src.clinching import ClinchingResult; import inspect; sig = inspect.signature(ClinchingResult); assert 'method' in sig.parameters and 'total_evals' in sig.parameters and 'relevant_games_count' in sig.parameters; print('OK')"`

- [x] 5. Checkpoint - Verify clinching module
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement server integration
  - [x] 6.1 Modify `_handle_get_clinch_estimate()` in `src/server.py` — remove `run_benchmark()` call, pass cache
    - Remove the explicit `run_benchmark(games)` call
    - Pass `cache=server.cache` to `estimate_clinching()`
    - _Requirements: 6.1, 6.3_
    - **Accept**: The estimate endpoint uses adaptive timing via cache instead of explicit benchmark
    - **Verify**: `python3 -m pytest tests/test_cp_clinch_endpoint.py -v`

  - [x] 6.2 Modify `_handle_post_clinching_scenarios()` in `src/server.py` — add timing measurement and cancellation handling
    - Add `import time` at top if not already imported
    - Record `start_time = time.perf_counter()` before calling `compute_clinching_scenarios()`
    - Do NOT pass `cache` to `compute_clinching_scenarios()` (function no longer accepts it)
    - After serializing the result, wrap `self._send_json_response(200, response)` in try/except BrokenPipeError
    - If BrokenPipeError is raised: return immediately without storing timing (user cancelled)
    - After successful send: compute `elapsed_seconds = time.perf_counter() - start_time`
    - Compute `ms_per_eval = (elapsed_seconds * 1000) / result.total_evals`
    - Call `server.cache.store_solver_timing(ms_per_eval=ms_per_eval, method=result.method, relevant_games_count=result.relevant_games_count, total_evals=result.total_evals)`
    - Guard with `if result.total_evals > 0` to prevent division by zero
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 6.2_
    - **Accept**: `pytest tests/test_server_timing.py` — all 4 tests pass; timing stored only after successful delivery
    - **Verify**: `python3 -m pytest tests/test_server_timing.py -v`

  - [x] 6.3 Add `GET /api/solver-timings` endpoint to `src/server.py`
    - Add a new route handler `_handle_get_solver_timings()` that calls `server.cache.get_solver_timings()`
    - Compute count and avg_ms_per_eval from the returned records
    - Return JSON response: `{"timings": [...], "count": N, "avg_ms_per_eval": X.XX}`
    - Register the route in the server's URL dispatcher for GET /api/solver-timings
    - _Requirements: 8.5_
    - **Accept**: `curl http://localhost:8080/api/solver-timings` returns valid JSON with keys timings, count, avg_ms_per_eval
    - **Verify**: `python3 -c "from src.server import NFLRequestHandler; assert hasattr(NFLRequestHandler, '_handle_get_solver_timings'); print('OK')"`

  - [x] 6.4 Add `solverTimings()` function to `frontend/js/api.js`
    - Add a new function `solverTimings()` that calls `GET /api/solver-timings` via the `request()` helper
    - Export it in the IIFE's return object
    - _Requirements: 8.2_
    - **Accept**: `API.solverTimings` is a function that returns a Promise
    - **Verify**: `grep -n "solverTimings" frontend/js/api.js | head -5`

  - [x] 6.5 Add "Timing History" button and modal to `frontend/js/simulation.js`
    - Add a `btn-sm btn-outline-info` button labeled "Timing History" in the clinching section's flex container (next to the "Clinching Scenarios" button)
    - Append a Bootstrap modal to the DOM (id="timingHistoryModal") on first use
    - On click: fetch timing data via `API.solverTimings()`, render table in modal body, show modal
    - Modal displays: title "Solver Timing History", explanatory paragraph, summary line (count + avg), scrollable table with columns (ms/eval, Method, Games, Evaluations, Recorded At)
    - Handle empty state: show info alert "No timing data collected yet. Run the clinching solver to start building calibration data."
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
    - **Accept**: The clinching section renders a "Timing History" button; clicking it opens a modal with timing data or empty-state message
    - **Verify**: `grep -n "Timing History" frontend/js/simulation.js | head -5`

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - **Verify**: `python3 -m pytest tests/ -v`

- [ ]* 8. Write property-based tests for correctness properties
  - [ ]* 8.1 Write property test for store/retrieve round trip
    - **Property 1: Store/Retrieve Round Trip**
    - **Validates: Requirements 1.3, 3.3**
    - Use Hypothesis to generate arbitrary valid timing data (positive ms_per_eval, method in {"enumeration", "sampling"}, positive counts)
    - Assert stored record matches retrieved record on all fields
    - _Requirements: 1.3, 3.3_

  - [ ]* 8.2 Write property test for rolling window size invariant
    - **Property 2: Rolling Window Size Invariant**
    - **Validates: Requirements 3.1, 3.2, 7.1**
    - Use Hypothesis to generate sequences of N store operations (1 <= N <= 100)
    - Assert `get_solver_timings()` returns exactly min(N, 50) records
    - Assert table never contains more than 50 records
    - _Requirements: 3.1, 3.2, 7.1_

  - [ ]* 8.3 Write property test for adaptive mean estimation
    - **Property 3: Adaptive Mean Estimation**
    - **Validates: Requirements 4.1, 5.2**
    - Use Hypothesis to generate lists of 1-50 positive floats, store them as ms_per_eval values
    - Assert `get_ms_per_eval(cache=cache)` equals arithmetic mean within floating-point tolerance
    - _Requirements: 4.1, 5.2_

  - [ ]* 8.4 Write property test for cache-None backward compatibility
    - **Property 4: Cache-None Backward Compatibility**
    - **Validates: Requirements 5.3**
    - Use Hypothesis to generate positive floats for the module-level global
    - Patch `_benchmark_ms_per_eval` to the generated value
    - Assert `get_ms_per_eval(cache=None)` returns that value without DB access
    - _Requirements: 5.3_

  - [ ]* 8.5 Write property test for cancellation safety
    - **Property 5: Cancellation Safety**
    - **Validates: Requirements 2.2, 6.2**
    - Mock `_send_json_response` to raise BrokenPipeError
    - Assert `store_solver_timing` is never called
    - Assert timing store record count is unchanged after the request
    - _Requirements: 2.2, 6.2_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Timing storage moved from `compute_clinching_scenarios()` to `_handle_post_clinching_scenarios()` in the server layer
- `compute_clinching_scenarios()` does NOT accept a `cache` parameter — it exposes metadata (method, total_evals, relevant_games_count) in ClinchingResult for the server to use
- BrokenPipeError on response write indicates user cancellation (AbortController abort) — no timing is stored in this case
- Use `TYPE_CHECKING` guard for `Cache` import in `clinching.py` to avoid circular imports
- In-memory SQLite (`:memory:`) is used for all test fixtures to ensure isolation and speed

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3"] },
    { "id": 5, "tasks": ["6.1", "6.2", "6.3"] },
    { "id": 6, "tasks": ["6.4", "6.5"] },
    { "id": 7, "tasks": ["8.1", "8.2", "8.3", "8.4", "8.5"] }
  ]
}
```
