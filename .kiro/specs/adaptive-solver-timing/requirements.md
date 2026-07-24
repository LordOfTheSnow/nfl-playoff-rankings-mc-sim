# Requirements Document

## Introduction

The Adaptive Solver Time Estimation feature replaces the current synthetic benchmark approach for clinching solver runtime estimation with a historical-data-driven model. Instead of running 100 artificial iterations every 24 hours to estimate ms/eval, the system records actual solver performance after each `compute_clinching_scenarios()` run and uses the rolling average of the last 50 measurements to produce more accurate time estimates. The existing `run_benchmark()` function remains as a cold-start seed when no historical data exists.

Timing measurements are recorded at the server layer (Scenarios_Endpoint) only after the response has been successfully delivered to the client. If the client disconnects before receiving the response (e.g., user cancels via AbortController in the frontend), no timing data is stored. This ensures the timing database reflects only complete, successfully-served solver runs.

## Glossary

- **Solver_Timing_Store**: The SQLite table within `nfl_cache.db` that persists solver performance measurements, managed via the `Cache` class.
- **Measurement_Record**: A single row in the Solver_Timing_Store containing ms_per_eval, method, relevant_games_count, total_evals, and a timestamp.
- **Clinching_Module**: The `src/clinching.py` module containing `run_benchmark()`, `get_ms_per_eval()`, `estimate_clinching()`, and `compute_clinching_scenarios()`.
- **Cache_Module**: The `src/cache.py` module containing the `Cache` class with SQLite access.
- **Estimation_Endpoint**: The `GET /api/clinch-estimate` API handler in `src/server.py`.
- **Scenarios_Endpoint**: The `POST /api/clinching-scenarios` API handler in `src/server.py`.
- **Rolling_Window**: The last 50 Measurement_Records ordered by timestamp descending, used to compute the average ms_per_eval.

## Requirements

### Requirement 1: Measurement Storage Schema

**User Story:** As a system maintainer, I want solver performance data stored persistently in SQLite, so that estimation accuracy improves over time and survives application restarts.

#### Acceptance Criteria

1. THE Cache_Module SHALL define a `solver_timing` table in `nfl_cache.db` with columns: `id` (INTEGER PRIMARY KEY AUTOINCREMENT), `ms_per_eval` (REAL NOT NULL), `method` (TEXT NOT NULL), `relevant_games_count` (INTEGER NOT NULL), `total_evals` (INTEGER NOT NULL), and `recorded_at` (TEXT NOT NULL).
2. WHEN the Cache_Module initializes, THE Cache_Module SHALL create the `solver_timing` table if it does not already exist.
3. THE Cache_Module SHALL provide a `store_solver_timing` method that accepts ms_per_eval, method, relevant_games_count, and total_evals as parameters and inserts a Measurement_Record with the current UTC timestamp.

### Requirement 2: Measurement Recording After Successful Response Delivery

**User Story:** As a system operator, I want actual solver performance recorded automatically only after the response is successfully delivered to the client, so that cancelled requests do not pollute the timing data.

#### Acceptance Criteria

1. WHEN the Scenarios_Endpoint completes a solver run and successfully delivers the response to the client, THE Scenarios_Endpoint SHALL record a Measurement_Record containing the elapsed wall-clock time divided by the number of evaluations performed (ms_per_eval), the method used (enumeration or sampling), the count of relevant other games, and the total number of evaluations.
2. IF the client disconnects before receiving the response (user cancellation via AbortController causing BrokenPipeError on response write), THEN THE Scenarios_Endpoint SHALL NOT store a Measurement_Record.
3. IF `compute_clinching_scenarios()` returns a result with an error field set, THEN THE Scenarios_Endpoint SHALL skip recording a Measurement_Record.
4. THE Scenarios_Endpoint SHALL compute ms_per_eval as `(elapsed_seconds * 1000) / total_evals` where elapsed_seconds is the wall-clock time from before the solver call to after successful response delivery, and total_evals is the actual number of universe evaluations performed.

### Requirement 3: Historical Data Retrieval

**User Story:** As a developer, I want a method to retrieve the most recent solver timing measurements, so that estimation logic can compute a rolling average.

#### Acceptance Criteria

1. THE Cache_Module SHALL provide a `get_solver_timings` method that returns the most recent 50 Measurement_Records ordered by `recorded_at` descending.
2. WHEN the `solver_timing` table contains fewer than 50 records, THE `get_solver_timings` method SHALL return all available records.
3. THE `get_solver_timings` method SHALL return each record as a dictionary with keys: ms_per_eval, method, relevant_games_count, total_evals, and recorded_at.

### Requirement 4: Adaptive ms_per_eval Estimation

**User Story:** As an end user requesting a clinching time estimate, I want the estimate to reflect actual solver performance on my hardware, so that the predicted runtime is accurate.

#### Acceptance Criteria

1. WHEN `get_ms_per_eval()` is called and the Solver_Timing_Store contains one or more Measurement_Records, THE Clinching_Module SHALL return the arithmetic mean of the ms_per_eval values from the Rolling_Window.
2. WHEN `get_ms_per_eval()` is called and the Solver_Timing_Store contains zero Measurement_Records, THE Clinching_Module SHALL fall back to executing `run_benchmark()` with the provided games data.
3. WHEN `get_ms_per_eval()` is called without games data and the Solver_Timing_Store contains zero Measurement_Records, THE Clinching_Module SHALL return a conservative default of 2.0 ms.

### Requirement 5: Cache Dependency Injection

**User Story:** As a developer, I want the clinching estimation functions to accept a Cache instance, so that historical timing data can be accessed without global state.

#### Acceptance Criteria

1. THE `get_ms_per_eval()` function SHALL accept an optional `cache` parameter of type `Cache` or None.
2. WHEN a `cache` parameter is provided, THE `get_ms_per_eval()` function SHALL query the Solver_Timing_Store via `cache.get_solver_timings()`.
3. WHEN no `cache` parameter is provided or `cache` is None, THE `get_ms_per_eval()` function SHALL fall back to the existing benchmark behavior with module-level globals.
4. THE `estimate_clinching()` function SHALL accept an optional `cache` parameter and pass it through to `get_ms_per_eval()`.
5. THE `compute_clinching_scenarios()` function SHALL NOT accept a `cache` parameter; timing storage is the responsibility of the server layer.

### Requirement 6: Server Integration

**User Story:** As an API consumer, I want the clinch-estimate endpoint to use adaptive timing and the clinching-scenarios endpoint to record measurements only after successful delivery, so that accuracy improves with each completed solver run.

#### Acceptance Criteria

1. WHEN the Estimation_Endpoint handles a request, THE Estimation_Endpoint SHALL pass the server's Cache instance to `estimate_clinching()`.
2. WHEN the Scenarios_Endpoint completes a solver run and successfully writes the JSON response to the client, THE Scenarios_Endpoint SHALL call `cache.store_solver_timing()` with the computed ms_per_eval, method, relevant_games_count, and total_evals. The response write SHALL be wrapped in a try/except for BrokenPipeError; if BrokenPipeError is raised (indicating user cancellation), timing storage SHALL be skipped.
3. THE Estimation_Endpoint SHALL no longer call `run_benchmark()` explicitly; adaptive estimation via `get_ms_per_eval()` with the cache replaces the manual benchmark trigger.

### Requirement 7: Rolling Window Maintenance

**User Story:** As a system operator, I want the measurement store to retain only the most relevant recent data, so that stale measurements from different hardware or software versions do not degrade estimation accuracy.

#### Acceptance Criteria

1. WHEN the Solver_Timing_Store contains more than 50 Measurement_Records, THE Cache_Module SHALL retain only the 50 most recent records by `recorded_at` timestamp, deleting older records during each `store_solver_timing()` call.

### Requirement 8: Timing History Display

**User Story:** As a user, I want to view the stored solver timing history from the clinching section, so that I can understand how estimates are calibrated and whether the system has sufficient data.

#### Acceptance Criteria

1. THE Clinching Scenarios section SHALL display a "Timing History" button next to the existing "Clinching Scenarios" button.
2. WHEN the user clicks the "Timing History" button, THE frontend SHALL fetch timing data from GET /api/solver-timings and display it in a modal dialog (Bootstrap modal).
3. THE modal SHALL display a headline for each column (ms/eval, Method, Games, Evaluations, Recorded At) and an explanatory text explaining that these measurements are used to improve time estimates.
4. WHEN the Solver_Timing_Store contains zero records, THE modal SHALL display a message indicating no timing data is available yet and that data will be collected after the first solver run.
5. THE server SHALL provide a GET /api/solver-timings endpoint that returns the stored timing records as a JSON array.
