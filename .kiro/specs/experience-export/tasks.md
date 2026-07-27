# Implementation Plan: Experience Export

## Overview

Implement a single-module feature (`src/experience_export.py`) that inserts solver performance entries into a grouped markdown table at `doc/solver-performance.md`. Entries are grouped by (CPU Model, CPU Cores) — the module reads existing content, parses rows into hardware groups, inserts the new row into the matching group, and rewrites the file. Uses standard library only. Test-first: test skeletons encode spec behavior before implementation.

## Tasks

- [x] 1. Write test skeletons encoding expected behavior
  - [x] 1.1 Create test file with all test cases for experience export
    - Create `tests/test_experience_export.py` with pytest test functions covering:
      - `SolverPerformanceEntry` dataclass construction
      - `format_table_row()` output format (pipe-delimited, field order: CPU Model | CPU Cores | Relevant Games | Wall Clock (s) | Method | Total Evals | Factor, 2 decimal places for wall clock, 1 decimal place for factor)
      - `format_table_row()` takes a `factor` parameter — test that factor appears as last column with 1 decimal place
      - `get_cpu_info()` return type and fallback logic
      - `_compute_factors()` — single entry returns [1.0]
      - `_compute_factors()` — multiple entries return correct factors relative to median
      - `_compute_factors()` — edge case with cpu_cores=0 or wall_clock=0 (treated as 0.0 throughput)
      - `_parse_and_insert_row()` inserting into an existing group (row appears after existing rows in same group)
      - `_parse_and_insert_row()` creating a new group when no match exists (new row appended at end)
      - `_parse_and_insert_row()` preserving all existing rows (none deleted or modified in first six columns)
      - `_parse_and_insert_row()` recalculates Factor values for all existing rows after new row insertion
      - `_parse_and_insert_row()` handling malformed rows gracefully (missing columns, non-integer cores)
      - `export_solver_performance()` file creation with header/table structure
      - `export_solver_performance()` grouping insertion via `_parse_and_insert_row()` when file exists
      - `export_solver_performance()` skip on error result
      - `export_solver_performance()` graceful I/O error handling
      - `export_solver_performance()` parent directory creation
    - Tests use `tmp_path` fixture for file operations, `unittest.mock.patch` for CPU info and I/O errors
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
    - **Accept**: `pytest tests/test_experience_export.py --collect-only` shows all test functions collected (tests will fail since implementation does not exist yet)

  - [x] 1.2 Create test file for docker-entrypoint.py `--perf-export-path` injection
    - Create `tests/test_docker_entrypoint_perf_export.py` with pytest test functions covering:
      - `resolve_config()` injects `--perf-export-path /data/doc/solver-performance.md` when absent from CMD args
      - `resolve_config()` does NOT inject `--perf-export-path` when already present in CMD args
      - `resolve_config()` preserves user-provided `--perf-export-path` value when specified
      - Injection ordering: `--perf-export-path` appears before CMD overrides
    - Tests import `resolve_config` from `docker-entrypoint` (use importlib since filename has a hyphen)
    - _Requirements: 7.2, 7.6_
    - **Accept**: `pytest tests/test_docker_entrypoint_perf_export.py --collect-only` shows all test functions collected

- [x] 2. Implement experience export module
  - [x] 2.1 Create `src/experience_export.py` with `SolverPerformanceEntry` dataclass and `get_cpu_info()`
    - Define `SolverPerformanceEntry` dataclass with fields: cpu_cores (int), cpu_model (str), relevant_games_count (int), wall_clock_seconds (float), method (str), total_evals (int)
    - Implement `get_cpu_info() -> tuple[int, str]` with `os.cpu_count()` fallback to 0 and `platform.processor()` fallback to `/proc/cpuinfo` fallback to "Unknown"
    - Implement private `_read_cpuinfo_model() -> str` helper
    - _Requirements: 1.1, 1.2, 1.3, 5.1, 5.2, 5.3, 5.4, 5.5_
    - **Accept**: `pytest tests/test_experience_export.py -k "cpu_info or dataclass or entry"` passes

  - [x] 2.2 Implement `_compute_factors()`, `format_table_row()`, `_parse_and_insert_row()`, and `export_solver_performance()`
    - Implement `_compute_factors(rows_data: list[tuple[int, float, int]]) -> list[float]` — computes per_core_throughput for each row (`total_evals / wall_clock_seconds / cpu_cores`), derives median via `statistics.median`, returns list of `per_core_throughput / median` for each row. Returns `[1.0] * len(rows_data)` for single entry or when median is 0. Handles cpu_cores=0 or wall_clock=0 as 0.0 throughput.
    - Implement `format_table_row(entry: SolverPerformanceEntry, factor: float) -> str` producing pipe-delimited markdown row with column order: CPU Model | CPU Cores | Relevant Games | Wall Clock (s) | Method | Total Evals | Factor (factor formatted to 1 decimal place)
    - Implement `_parse_and_insert_row(existing_content: str, new_row: str, cpu_model: str, cpu_cores: int) -> str` — parses existing file content into header and data rows, groups data rows by (cpu_model, cpu_cores), inserts new_row at the end of the matching group (or appends a new group at end), recalculates Factor column for ALL rows via `_compute_factors()`, and returns the full reassembled file content
    - Implement `export_solver_performance(result: ClinchingResult, wall_clock_seconds: float, output_path: str | None = None) -> None`
    - Handle: error result early return, file creation with header (when file doesn't exist, single entry gets factor=1.0), read-parse-insert-rewrite via `_parse_and_insert_row()` (when file exists), parent directory creation, OSError logging
    - Define module-level constants: `_FILE_HEADER`, `_TABLE_HEADER`, `_TABLE_SEPARATOR`
    - Use logger named `src.experience_export`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 6.1, 6.2, 6.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
    - **Accept**: `pytest tests/test_experience_export.py` passes — all test cases green including factor computation tests

  - [x] 2.3 Modify `docker-entrypoint.py` to inject `--perf-export-path`
    - Add injection of `--perf-export-path /data/doc/solver-performance.md` in `resolve_config()` following the same pattern as `--db-path`
    - Inject only when `--perf-export-path` is not already present in `cmd_args`
    - Place the injection after the existing `--db-path` block, before the `args.extend(cmd_args)` line
    - _Requirements: 7.2, 7.6_
    - **Accept**: `pytest tests/test_docker_entrypoint_perf_export.py` passes — all test cases green

  - [x] 2.4 Modify `src/server.py` to accept `--perf-export-path` and pass it to `export_solver_performance()`
    - Add `--perf-export-path` argument to the server's `argparse.ArgumentParser` (type=str, default=None)
    - Store the parsed value as `self.server.perf_export_path` on the HTTPServer instance
    - In `_handle_post_clinching_scenarios()`, import and call `export_solver_performance(result, elapsed, output_path=self.server.perf_export_path)`
    - When `--perf-export-path` is not provided, pass `None` so the export function uses its default path
    - _Requirements: 7.1, 7.3, 7.4, 7.5_
    - **Accept**: `pytest tests/test_docker_entrypoint_perf_export.py tests/test_experience_export.py` passes

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Property-based tests and integration
  - [ ]* 4.1 Write property test for markdown row format
    - **Property 1: Markdown row contains all entry fields in correct order**
    - **Validates: Requirements 2.1, 2.5, 3.4**
    - Use Hypothesis to generate arbitrary `SolverPerformanceEntry` instances
    - Assert row starts with `| `, ends with `|\n`, contains all fields in order, wall_clock_seconds has exactly 2 decimal places

  - [ ]* 4.2 Write property test for file creation structure
    - **Property 2: File creation produces valid markdown table structure**
    - **Validates: Requirements 2.2, 2.3**
    - Generate arbitrary valid entries, call `export_solver_performance()` on a non-existent file
    - Assert file starts with `# Solver Performance\n\n`, followed by table header, separator, and one data row

  - [ ]* 4.3 Write property test for data preservation with grouping
    - **Property 3: Data preservation with grouping**
    - **Validates: Requirements 2.4, 3.1, 3.3, 3.6**
    - Generate arbitrary existing file content with valid grouped rows and a new entry
    - Assert all original data rows appear unmodified in the output — no rows deleted or altered — while the file is rewritten to maintain correct hardware group ordering

  - [ ]* 4.4 Write property test for ClinchingResult field flow-through
    - **Property 4: ClinchingResult fields flow through to formatted output**
    - **Validates: Requirements 1.4, 4.3**
    - Generate arbitrary ClinchingResult (error=None) and wall_clock_seconds
    - Assert exported row contains relevant_games_count, method, and total_evals as substrings

  - [ ]* 4.5 Write property test for error result skip
    - **Property 5: Error result skips export entirely**
    - **Validates: Requirements 6.2**
    - Generate ClinchingResult with error not None
    - Assert no file created or modified

  - [ ]* 4.6 Write property test for I/O error graceful handling
    - **Property 6: I/O errors are swallowed gracefully**
    - **Validates: Requirements 6.1**
    - Patch file open to raise OSError, assert no exception raised and warning logged

  - [ ]* 4.7 Write property test for docker entrypoint `--perf-export-path` injection
    - **Property 7: Docker entrypoint injects --perf-export-path when absent**
    - **Validates: Requirements 7.2, 7.6**
    - Use Hypothesis to generate arbitrary CMD argument lists that do NOT contain `--perf-export-path`
    - Assert `resolve_config()` output contains `["--perf-export-path", "/data/doc/solver-performance.md"]`
    - Also generate CMD args that DO contain `--perf-export-path` and assert no duplicate injection

  - [ ]* 4.8 Write property test for grouping correctness
    - **Property 8: Entries are grouped by (CPU Model, CPU Cores)**
    - **Validates: Requirements 2.4, 3.1, 3.2, 3.6**
    - Use Hypothesis to generate a sequence of `export_solver_performance()` calls with varying hardware configurations
    - Assert that after each call, all rows sharing the same (cpu_model, cpu_cores) combination appear consecutively — no row from a different hardware group separates rows of the same group

  - [ ]* 4.9 Write property test for factor correctness
    - **Property 9: Factor correctness**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6**
    - Use Hypothesis to generate arbitrary sets of entries (varying cpu_cores, wall_clock_seconds, total_evals)
    - Assert that for any set of entries, each entry's Factor equals `per_core_throughput / median_per_core_throughput` formatted to 1 decimal place, where `per_core_throughput = total_evals / wall_clock_seconds / cpu_cores`
    - Assert that when the file contains only one entry, the Factor is 1.0
    - Assert that factors are recalculated correctly when a new entry is added

- [x] 5. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- No new dependencies needed — standard library only (os, platform, logging, pathlib, dataclasses)
- Hypothesis is already available in the project (`.hypothesis/` directory exists)
- Python 3.11+, pytest for tests

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["2.4"] },
    { "id": 4, "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9"] }
  ]
}
```
