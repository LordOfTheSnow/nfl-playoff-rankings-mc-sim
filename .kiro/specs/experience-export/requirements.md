# Requirements Document

## Introduction

The Experience Export feature adds an opt-in mechanism to export solver performance data from the clinching scenario solver to a human-readable markdown file (`doc/solver-performance.md`). After a successful solver run, callers can trigger an export that inserts a new row into a markdown table documenting CPU configuration, solver complexity, method, and wall-clock time. Results are grouped by CPU Model and CPU Cores so that entries from the same hardware appear together. The file serves as a reference table on the GitHub project page so users can evaluate whether their platform is suitable for running the solver.

## Glossary

- **Experience_Export_Module**: The new `src/experience_export.py` module responsible for formatting markdown table entries and writing them to the performance file.
- **Performance_File**: The markdown file at `doc/solver-performance.md` that accumulates solver performance entries as a table.
- **Solver_Entry**: A single performance measurement containing CPU model, CPU cores, relevant_games_count, wall-clock time, method, and total_evals.
- **Clinching_Module**: The `src/clinching.py` module containing `compute_clinching_scenarios()` and the `ClinchingResult` dataclass.
- **ClinchingResult**: The dataclass returned by `compute_clinching_scenarios()` containing total_evals, relevant_games_count, method, and exhaustive fields.
- **Server**: The `src/server.py` module that handles HTTP endpoints and CLI argument parsing for the application.
- **docker-entrypoint.py**: The container entrypoint script that resolves environment variables and injects default container paths into the application command line.
- **Hardware_Group**: A set of rows in the Performance_File that share the same combination of CPU Model and CPU Cores values.
- **Per_Core_Throughput**: `total_evals / wall_clock_seconds / cpu_cores` — the raw efficiency metric for a single entry.
- **Baseline**: The median Per_Core_Throughput across all entries in the Performance_File.
- **Factor**: `Per_Core_Throughput / Baseline` — how much faster (>1.0) or slower (<1.0) a hardware/run is compared to the median.

## Requirements

### Requirement 1: Performance Entry Data Collection

**User Story:** As a developer, I want to capture all relevant solver performance metadata in a structured format, so that each export entry is complete and useful for platform comparison.

#### Acceptance Criteria

1. THE Experience_Export_Module SHALL define a dataclass or typed dictionary named `SolverPerformanceEntry` with fields: cpu_model (str), cpu_cores (int), relevant_games_count (int), wall_clock_seconds (float), method (str), and total_evals (int).
2. THE Experience_Export_Module SHALL obtain cpu_cores from `os.cpu_count()`.
3. THE Experience_Export_Module SHALL obtain cpu_model from `platform.processor()` or by reading `/proc/cpuinfo` model name when `platform.processor()` returns an empty string.
4. THE Experience_Export_Module SHALL derive relevant_games_count, method, and total_evals from the ClinchingResult returned by the solver.

### Requirement 2: Markdown Table Formatting

**User Story:** As a GitHub page reader, I want solver performance entries formatted as a clean markdown table, so that I can quickly scan and compare platform performance.

#### Acceptance Criteria

1. THE Experience_Export_Module SHALL format each Solver_Entry as a single markdown table row with columns in this order: CPU Model, CPU Cores, Relevant Games, Wall Clock (s), Method, Total Evals, Factor.
2. THE Performance_File SHALL contain a markdown header (`# Solver Performance`) and a table header row with column names (CPU Model, CPU Cores, Relevant Games, Wall Clock (s), Method, Total Evals, Factor) and a separator row, followed by data rows.
3. WHEN the Performance_File does not exist, THE Experience_Export_Module SHALL create the file with the markdown header, table header row, separator row, and the first data row.
4. WHEN the Performance_File already exists, THE Experience_Export_Module SHALL insert the new data row within the Hardware_Group matching the entry's CPU Model and CPU Cores combination.
5. THE Experience_Export_Module SHALL format wall_clock_seconds with two decimal places.
6. THE Experience_Export_Module SHALL format method as the literal string from ClinchingResult (either "enumeration" or "sampling").

### Requirement 3: File Update Operations

**User Story:** As a project maintainer, I want the performance file to group entries by hardware and preserve all historical data, so that results are easy to compare and no measurements are lost.

#### Acceptance Criteria

1. WHEN the Performance_File exists and contains valid content, THE Experience_Export_Module SHALL read the existing file, locate the Hardware_Group matching the new entry's CPU Model and CPU Cores, and insert the new row within that group.
2. WHEN no Hardware_Group matching the new entry's CPU Model and CPU Cores exists in the Performance_File, THE Experience_Export_Module SHALL append a new group containing the new row at the end of the file.
3. THE Experience_Export_Module SHALL NOT delete or modify any existing data in the first six columns (CPU Model, CPU Cores, Relevant Games, Wall Clock (s), Method, Total Evals) when rewriting the Performance_File.
4. IF the Performance_File path does not exist and the parent directory does not exist, THEN THE Experience_Export_Module SHALL create the parent directory before writing.
5. THE Experience_Export_Module SHALL ensure each data row ends with a newline character.
6. THE Experience_Export_Module SHALL rewrite the Performance_File to maintain Hardware_Group ordering while preserving all previous data rows intact in their first six columns.
7. WHEN the Performance_File is rewritten (for grouping or insertion), THE Experience_Export_Module SHALL recalculate the Factor column for ALL rows in the file, because the Baseline (median Per_Core_Throughput) changes when a new entry is added.

### Requirement 4: Opt-In Export Trigger

**User Story:** As a developer integrating the export, I want to trigger the export explicitly via a function call, so that performance data is only written when intentionally requested.

#### Acceptance Criteria

1. THE Experience_Export_Module SHALL expose a public function `export_solver_performance` that accepts a ClinchingResult and a wall_clock_seconds float as parameters.
2. THE `export_solver_performance` function SHALL accept an optional `output_path` parameter defaulting to `doc/solver-performance.md` (relative to the project root).
3. WHEN `export_solver_performance` is called, THE Experience_Export_Module SHALL collect CPU metadata, format the entry, and insert it into the Performance_File at the correct Hardware_Group position.
4. THE `export_solver_performance` function SHALL NOT be called automatically by `compute_clinching_scenarios()`; the caller is responsible for invoking it.

### Requirement 5: CPU Metadata Retrieval

**User Story:** As a user comparing solver performance across platforms, I want CPU information captured accurately, so that I can correlate performance with hardware.

#### Acceptance Criteria

1. THE Experience_Export_Module SHALL retrieve the CPU core count using `os.cpu_count()`.
2. IF `os.cpu_count()` returns None, THEN THE Experience_Export_Module SHALL record cpu_cores as 0.
3. THE Experience_Export_Module SHALL retrieve the CPU model name using `platform.processor()`.
4. IF `platform.processor()` returns an empty string, THEN THE Experience_Export_Module SHALL attempt to read the model name from `/proc/cpuinfo` (first "model name" line).
5. IF both `platform.processor()` and `/proc/cpuinfo` fail to provide a model name, THEN THE Experience_Export_Module SHALL record cpu_model as "Unknown".

### Requirement 6: Error Handling

**User Story:** As a system operator, I want the export to fail gracefully without disrupting the solver workflow, so that a file I/O error does not crash the application.

#### Acceptance Criteria

1. IF a file I/O error occurs during export (PermissionError, OSError), THEN THE Experience_Export_Module SHALL log the error at WARNING level and return without raising an exception.
2. IF the ClinchingResult contains an error field that is not None, THEN THE `export_solver_performance` function SHALL skip the export and return immediately.
3. THE Experience_Export_Module SHALL use the standard `logging` module with a logger named `src.experience_export`.

### Requirement 7: Docker Bind Mount Compatibility

**User Story:** As a user running the simulator in Docker, I want the performance export file to persist on the host filesystem via the bind mount, so that exported data survives container restarts.

#### Acceptance Criteria

1. THE `export_solver_performance` function SHALL resolve the output_path parameter as an absolute path when an absolute path is provided, without prepending any prefix.
2. WHEN the docker-entrypoint.py constructs the application command and `--perf-export-path` is not already present in the CMD arguments, THE docker-entrypoint.py SHALL inject `--perf-export-path /data/doc/solver-performance.md` into the argument list.
3. THE Server SHALL accept a `--perf-export-path` command-line argument specifying the absolute path for the performance export file.
4. WHEN the Server receives a `--perf-export-path` argument, THE Server SHALL pass the configured path as the output_path parameter to `export_solver_performance`.
5. WHEN the `--perf-export-path` argument is not provided to the Server, THE Server SHALL pass None as the output_path parameter, causing `export_solver_performance` to use the default relative path `doc/solver-performance.md`.
6. THE docker-entrypoint.py SHALL follow the same injection pattern used for `--db-path`: inject the default container path only when the argument is not already present in CMD overrides.

### Requirement 8: Performance Factor Calculation

**User Story:** As a user comparing solver performance across platforms, I want a normalized per-core throughput factor displayed alongside each entry, so that I can immediately see which hardware configurations are faster or slower relative to the median.

#### Acceptance Criteria

1. THE Experience_Export_Module SHALL compute Per_Core_Throughput for each entry as `total_evals / wall_clock_seconds / cpu_cores`.
2. THE Experience_Export_Module SHALL compute the Baseline as the median of Per_Core_Throughput values across ALL entries in the Performance_File.
3. THE Experience_Export_Module SHALL compute the Factor for each entry as `Per_Core_Throughput / Baseline`.
4. THE Experience_Export_Module SHALL display the Factor with exactly one decimal place (e.g., "2.3" or "0.7").
5. WHEN the Performance_File contains only one entry, THE Experience_Export_Module SHALL set that entry's Factor to 1.0.
6. WHEN a new entry is added to the Performance_File, THE Experience_Export_Module SHALL recalculate the Factor for ALL existing entries in the file (because the Baseline changes with each new entry).
7. THE Experience_Export_Module SHALL place the Factor column as the last column in the table row, after Total Evals.
