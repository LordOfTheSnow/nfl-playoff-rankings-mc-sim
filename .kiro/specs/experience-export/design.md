# Design: Experience Export

## Context

The clinching scenario solver (`src/clinching.py`) performs computationally expensive evaluations. Users want to compare solver performance across platforms (CPU, complexity). This module provides an opt-in mechanism to append performance entries to a markdown table at `doc/solver-performance.md`, which renders as a reference on the GitHub project page.

The server endpoint `_handle_post_clinching_scenarios()` already measures wall-clock time via `time.perf_counter()`. The new module simply receives the result and timing as arguments.

## Architecture

Single new module `src/experience_export.py` with no external dependencies beyond the standard library (`os`, `platform`, `logging`, `pathlib`, `dataclasses`, `statistics`). In Docker, `docker-entrypoint.py` injects `--perf-export-path /data/doc/solver-performance.md` so the export file lands on the host via the bind mount.

```
┌──────────────────────┐       ┌─────────────────────────┐
│ docker-entrypoint.py │       │ src/experience_export.py │
│                      │       │                          │
│ injects:             │       │ export_solver_           │
│ --perf-export-path   │       │  performance()           │
│   /data/doc/solver-  │       │                          │
│   performance.md     │       │ - collect CPU metadata   │
└──────────┬───────────┘       │ - format markdown row    │
           │ args              │ - group & insert to file │
           ▼                   └────────────▲────────────┘
┌──────────────────────┐                    │
│  src/server.py       │                    │ calls
│                      │────────────────────┘
│ --perf-export-path   │
│ _handle_post_        │
│  clinching_scenarios │
│ (measures wall_clock)│
└──────────────────────┘
                               ┌─────────────────────────┐
┌──────────────────────┐       │ /data/doc/solver-        │
│  src/clinching.py    │       │   performance.md         │
│                      │       │ (Docker)                 │
│ ClinchingResult      │       │                          │
│ (dataclass)          │       │ doc/solver-performance.md│
└──────────────────────┘       │ (local/no Docker)        │
                               └─────────────────────────┘
```

## Components

### `SolverPerformanceEntry` (dataclass)

Holds all fields for a single performance row:

```python
from dataclasses import dataclass


@dataclass
class SolverPerformanceEntry:
    """A single solver performance measurement.

    Note: The Factor column is computed at write time from raw data
    (total_evals, wall_clock_seconds, cpu_cores) across ALL entries in
    the file. It is not stored in this dataclass because it depends on
    the full dataset (median per_core_throughput).
    """

    cpu_model: str
    cpu_cores: int
    relevant_games_count: int
    wall_clock_seconds: float
    method: str
    total_evals: int
```

### `get_cpu_info() -> tuple[int, str]`

Retrieves CPU metadata with fallback logic:

```python
import os
import platform


def get_cpu_info() -> tuple[int, str]:
    """Return (cpu_cores, cpu_model) with fallback logic.

    - cpu_cores: os.cpu_count() or 0 if None
    - cpu_model: platform.processor(), falling back to /proc/cpuinfo,
      falling back to "Unknown"
    """
    cpu_cores = os.cpu_count() or 0

    cpu_model = platform.processor()
    if not cpu_model:
        cpu_model = _read_cpuinfo_model()

    return cpu_cores, cpu_model


def _read_cpuinfo_model() -> str:
    """Read CPU model from /proc/cpuinfo. Returns 'Unknown' on failure."""
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("model name"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        return parts[1].strip()
    except OSError:
        pass
    return "Unknown"
```

### `format_table_row(entry: SolverPerformanceEntry, factor: float) -> str`

Formats a single entry as a markdown table row. The `factor` parameter is computed externally by `_compute_factors()` and passed in:

```python
def format_table_row(entry: SolverPerformanceEntry, factor: float) -> str:
    """Format entry as a markdown table row.

    Columns: CPU Model | CPU Cores | Relevant Games | Wall Clock (s) | Method | Total Evals | Factor
    """
    return (
        f"| {entry.cpu_model} "
        f"| {entry.cpu_cores} "
        f"| {entry.relevant_games_count} "
        f"| {entry.wall_clock_seconds:.2f} "
        f"| {entry.method} "
        f"| {entry.total_evals} "
        f"| {factor:.1f} |\n"
    )
```

### `_compute_factors(rows_data: list[tuple[int, float, int]]) -> list[float]`

Computes the normalized performance factor for each row based on per-core throughput relative to the median:

```python
import statistics


def _compute_factors(rows_data: list[tuple[int, float, int]]) -> list[float]:
    """Compute performance factors for all rows.

    Args:
        rows_data: List of (cpu_cores, wall_clock_seconds, total_evals) for each row.

    Returns:
        List of factor values (per_core_throughput / median) for each row.
        Returns [1.0] * len(rows_data) if only one entry or median is 0.
    """
    if len(rows_data) <= 1:
        return [1.0] * len(rows_data)

    per_core_throughputs: list[float] = []
    for cpu_cores, wall_clock_seconds, total_evals in rows_data:
        if cpu_cores == 0 or wall_clock_seconds == 0.0:
            per_core_throughputs.append(0.0)
        else:
            per_core_throughputs.append(total_evals / wall_clock_seconds / cpu_cores)

    median_throughput = statistics.median(per_core_throughputs)

    if median_throughput == 0.0:
        return [1.0] * len(rows_data)

    return [t / median_throughput for t in per_core_throughputs]
```

### `_parse_and_insert_row(existing_content: str, new_row: str, cpu_model: str, cpu_cores: int) -> str`

Handles reading, grouping, inserting a new row into an existing file's content, and recalculating the Factor column for all rows:

```python
def _parse_and_insert_row(
    existing_content: str, new_row: str, cpu_model: str, cpu_cores: int
) -> str:
    """Parse existing file content, insert new_row into the correct hardware group.

    Groups are keyed by (cpu_model, cpu_cores). The new row is inserted at the
    end of its matching group. If no matching group exists, the new row is
    appended at the end of the file (creating a new group).

    After insertion, recalculates the Factor column for ALL rows based on the
    new median per_core_throughput.

    Args:
        existing_content: Full content of the existing performance file.
        new_row: Formatted markdown table row to insert (Factor column will be
                 recalculated, so its initial value does not matter).
        cpu_model: CPU model of the new entry (for group matching).
        cpu_cores: CPU core count of the new entry (for group matching).

    Returns:
        The full file content with the new row inserted at the correct position
        and all Factor columns recalculated.
    """
    lines = existing_content.split("\n")
    header_lines: list[str] = []
    data_rows: list[str] = []

    # Separate header (markdown title, blank lines, table header, separator)
    # from data rows
    in_data = False
    for line in lines:
        if in_data:
            if line.startswith("|"):
                data_rows.append(line)
        else:
            header_lines.append(line)
            # After the separator row (| --- | ...), data begins
            if line.startswith("| ---"):
                in_data = True

    # Parse data rows into groups keyed by (cpu_model, cpu_cores)
    # Preserve original group order
    groups: list[tuple[tuple[str, int], list[str]]] = []
    group_index: dict[tuple[str, int], int] = {}

    for row in data_rows:
        cols = [c.strip() for c in row.split("|")]
        # cols[0] is empty (before first |), cols[1] = CPU Model, cols[2] = CPU Cores
        if len(cols) >= 3:
            row_model = cols[1]
            try:
                row_cores = int(cols[2])
            except ValueError:
                row_cores = 0
            key = (row_model, row_cores)
        else:
            key = ("", 0)

        if key not in group_index:
            group_index[key] = len(groups)
            groups.append((key, []))
        groups[group_index[key]][1].append(row)

    # Insert new row into matching group or create new group
    target_key = (cpu_model, cpu_cores)
    if target_key in group_index:
        groups[group_index[target_key]][1].append(new_row.rstrip("\n"))
    else:
        groups.append((target_key, [new_row.rstrip("\n")]))

    # Collect all rows in order for factor recalculation
    all_rows: list[str] = []
    for _key, rows in groups:
        all_rows.extend(rows)

    # Parse raw data from all rows for factor computation
    rows_data: list[tuple[int, float, int]] = []
    for row in all_rows:
        cols = [c.strip() for c in row.split("|")]
        # cols[2] = CPU Cores, cols[4] = Wall Clock (s), cols[6] = Total Evals
        try:
            r_cores = int(cols[2])
            r_wall = float(cols[4])
            r_evals = int(cols[6])
        except (ValueError, IndexError):
            r_cores, r_wall, r_evals = 0, 0.0, 0
        rows_data.append((r_cores, r_wall, r_evals))

    # Compute new factors for all rows
    factors = _compute_factors(rows_data)

    # Rewrite all rows with updated Factor column
    updated_rows: list[str] = []
    for row, factor in zip(all_rows, factors):
        cols = [c.strip() for c in row.split("|")]
        # Rebuild row with first 6 data columns + updated factor
        # cols layout: ['', col1, col2, col3, col4, col5, col6, maybe_col7, '']
        if len(cols) >= 7:
            rebuilt = (
                f"| {cols[1]} "
                f"| {cols[2]} "
                f"| {cols[3]} "
                f"| {cols[4]} "
                f"| {cols[5]} "
                f"| {cols[6]} "
                f"| {factor:.1f} |"
            )
            updated_rows.append(rebuilt)
        else:
            updated_rows.append(row)  # malformed, preserve as-is

    # Re-group updated rows (same order as before)
    idx = 0
    result_lines = header_lines[:]
    for _key, rows in groups:
        for _ in rows:
            result_lines.append(updated_rows[idx])
            idx += 1

    # Ensure trailing newline
    result = "\n".join(result_lines)
    if not result.endswith("\n"):
        result += "\n"

    return result
```

### `export_solver_performance(result, wall_clock_seconds, output_path=None)`

Public entry point that orchestrates the full export:

```python
import logging
from pathlib import Path

from src.clinching import ClinchingResult

logger = logging.getLogger("src.experience_export")

_FILE_HEADER = "# Solver Performance\n\n"
_TABLE_HEADER = "| CPU Model | CPU Cores | Relevant Games | Wall Clock (s) | Method | Total Evals | Factor |\n"
_TABLE_SEPARATOR = "| --- | --- | --- | --- | --- | --- | --- |\n"


def export_solver_performance(
    result: ClinchingResult,
    wall_clock_seconds: float,
    output_path: str | None = None,
) -> None:
    """Export solver performance to a markdown table file.

    Args:
        result: The ClinchingResult from the solver.
        wall_clock_seconds: Wall-clock time of the solver run.
        output_path: Path to the output file. Defaults to 'doc/solver-performance.md'.
    """
    if result.error is not None:
        return

    if output_path is None:
        output_path = "doc/solver-performance.md"

    cpu_cores, cpu_model = get_cpu_info()

    entry = SolverPerformanceEntry(
        cpu_model=cpu_model,
        cpu_cores=cpu_cores,
        relevant_games_count=result.relevant_games_count,
        wall_clock_seconds=wall_clock_seconds,
        method=result.method,
        total_evals=result.total_evals,
    )

    row = format_table_row(entry, factor=1.0)  # initial factor; recalculated on insert
    path = Path(output_path)

    try:
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            existing_content = path.read_text()
            new_content = _parse_and_insert_row(
                existing_content, row, cpu_model, cpu_cores
            )
            path.write_text(new_content)
        else:
            with open(path, "w") as f:
                f.write(_FILE_HEADER)
                f.write(_TABLE_HEADER)
                f.write(_TABLE_SEPARATOR)
                # Single entry: factor is always 1.0
                f.write(format_table_row(entry, factor=1.0))
    except OSError as e:
        logger.warning("Failed to export solver performance: %s", e)
```

## Docker Bind Mount Integration

### Container Path Resolution

The `compose.yaml` bind mount maps the project root on the host (`./`) to `/data` inside the container. The performance file must be written to `/data/doc/solver-performance.md` so it appears at `doc/solver-performance.md` on the host.

```
Host:       ./doc/solver-performance.md
Container:  /data/doc/solver-performance.md
```

### `docker-entrypoint.py` Modification

Follows the same injection pattern as `--db-path`:

```python
def resolve_config(env_vars: dict, cmd_args: list[str]) -> list[str]:
    # ... existing logic ...

    # Check if --db-path is in cmd_args
    if "--db-path" not in cmd_args:
        args.extend(["--db-path", "/data/nfl_cache.db"])

    # Check if --perf-export-path is in cmd_args
    if "--perf-export-path" not in cmd_args:
        args.extend(["--perf-export-path", "/data/doc/solver-performance.md"])

    # Append any CMD overrides
    args.extend(cmd_args)

    return args
```

### `src/server.py` CLI Argument Acceptance

The server's argument parser adds `--perf-export-path`:

```python
parser.add_argument(
    "--perf-export-path",
    type=str,
    default=None,
    help="Absolute path for the solver performance export file.",
)
```

When calling `export_solver_performance()`, the server passes the parsed value:

```python
from src.experience_export import export_solver_performance

# In _handle_post_clinching_scenarios():
export_solver_performance(
    result=clinching_result,
    wall_clock_seconds=elapsed,
    output_path=self.server.perf_export_path,  # None when not provided
)
```

### Path Resolution Logic

| Environment | `--perf-export-path` | `output_path` received | File written to |
|---|---|---|---|
| Docker (compose.yaml) | `/data/doc/solver-performance.md` (injected by entrypoint) | `/data/doc/solver-performance.md` | Host: `./doc/solver-performance.md` |
| Docker (manual override) | User-specified absolute path | That path | Wherever the user mapped it |
| Local (no Docker) | Not provided | `None` → default | `doc/solver-performance.md` (relative to CWD) |

## Data Flow

1. `docker-entrypoint.py` injects `--perf-export-path /data/doc/solver-performance.md` (unless overridden in CMD)
2. `src/server.py` parses `--perf-export-path` and stores it as `self.server.perf_export_path`
3. Server endpoint measures `wall_clock_seconds = time.perf_counter() - start_time`
4. Caller passes `ClinchingResult` + `wall_clock_seconds` + `output_path` to `export_solver_performance()`
5. Function checks `result.error` — returns early if set
6. If `output_path` is an absolute path, it is used as-is; if `None`, defaults to `doc/solver-performance.md`
7. `get_cpu_info()` collects platform metadata
8. `SolverPerformanceEntry` is constructed from result fields + CPU info
9. `format_table_row()` formats the entry as a pipe-delimited markdown row (with initial factor=1.0)
10. If the file does not exist: write header + table header + separator + row (factor=1.0 for single entry)
11. If the file exists: read content, call `_parse_and_insert_row()` which:
    a. Inserts the row into the correct hardware group
    b. Parses (cpu_cores, wall_clock_seconds, total_evals) from ALL rows
    c. Calls `_compute_factors()` to derive new factors based on median per_core_throughput
    d. Rewrites ALL rows with updated Factor column
    e. Returns the complete file content

## Error Handling

- **ClinchingResult.error is not None**: Skip export entirely (no file I/O)
- **os.cpu_count() returns None**: Record as 0
- **platform.processor() returns ""**: Fall back to `/proc/cpuinfo`
- **Both CPU model sources fail**: Record as "Unknown"
- **File I/O errors (PermissionError, OSError)**: Log at WARNING, return without raising
- **Parent directory missing**: Create with `mkdir(parents=True)`
- **Malformed existing rows (missing columns, non-integer cores)**: Assign to a fallback group key `("", 0)` and preserve the row as-is

## Output File Format

```markdown
# Solver Performance

| CPU Model | CPU Cores | Relevant Games | Wall Clock (s) | Method | Total Evals | Factor |
| --- | --- | --- | --- | --- | --- | --- |
| Intel(R) Core(TM) i7-10700K | 8 | 12 | 3.47 | enumeration | 531441 | 0.7 |
| Intel(R) Core(TM) i7-10700K | 8 | 9 | 1.82 | enumeration | 19683 | 0.5 |
| Apple M1 | 4 | 9 | 1.23 | enumeration | 19683 | 1.5 |
| AMD Ryzen 9 5950X | 16 | 14 | 8.92 | sampling | 10000 | 0.3 |
| AMD Ryzen 9 5950X | 16 | 12 | 2.14 | enumeration | 531441 | 5.9 |
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Markdown row contains all entry fields in correct order

*For any* valid `SolverPerformanceEntry` and *for any* factor float, the output of `format_table_row()` SHALL be a pipe-delimited string that starts with `| `, ends with `|\n`, and contains the fields cpu_model, cpu_cores, relevant_games_count, wall_clock_seconds (formatted to exactly 2 decimal places), method, total_evals, and factor (formatted to exactly 1 decimal place) in that order.

**Validates: Requirements 2.1, 2.5, 3.5, 8.4, 8.7**

### Property 2: File creation produces valid markdown table structure

*For any* valid `SolverPerformanceEntry`, when the output file does not exist, calling `export_solver_performance()` SHALL produce a file whose content begins with the markdown header `# Solver Performance\n\n`, followed by the table header row, separator row, and exactly one data row matching the entry.

**Validates: Requirements 2.2, 2.3**

### Property 3: Data preservation with grouping

*For any* existing file content containing valid data rows and *for any* valid `SolverPerformanceEntry`, calling `export_solver_performance()` SHALL result in a file that contains all original data rows with their first six columns (CPU Model, CPU Cores, Relevant Games, Wall Clock (s), Method, Total Evals) unmodified — no existing rows are deleted or altered in those columns — while the Factor column is recalculated for all rows and the file is rewritten to maintain correct hardware group ordering.

**Validates: Requirements 2.4, 3.1, 3.3, 3.6, 3.7**

### Property 4: ClinchingResult fields flow through to formatted output

*For any* `ClinchingResult` with `error=None` and *for any* `wall_clock_seconds` float, the exported row SHALL contain `result.relevant_games_count`, `result.method`, and `result.total_evals` as literal substrings within the pipe-delimited columns.

**Validates: Requirements 1.4, 4.3**

### Property 5: Error result skips export entirely

*For any* `ClinchingResult` where `error` is not None, calling `export_solver_performance()` SHALL not create or modify any file.

**Validates: Requirements 6.2**

### Property 6: I/O errors are swallowed gracefully

*For any* valid `SolverPerformanceEntry` and *for any* `OSError` raised during file operations, `export_solver_performance()` SHALL not raise an exception and SHALL log a warning.

**Validates: Requirements 6.1**

### Property 7: Docker entrypoint injects --perf-export-path when absent

*For any* set of CMD arguments that does not contain `--perf-export-path`, calling `resolve_config()` SHALL produce a final argument list that contains `["--perf-export-path", "/data/doc/solver-performance.md"]`. When `--perf-export-path` is already present in CMD arguments, `resolve_config()` SHALL not inject a duplicate.

**Validates: Requirements 7.2, 7.6**

### Property 8: Entries are grouped by (CPU Model, CPU Cores)

*For any* sequence of `export_solver_performance()` calls, after each call the resulting file SHALL have all rows sharing the same (cpu_model, cpu_cores) combination appearing consecutively — no row from a different hardware group separates rows of the same group.

**Validates: Requirements 2.4, 3.1, 3.2, 3.6**

### Property 9: Factor correctness

*For any* set of entries in the Performance_File, the Factor of each entry SHALL equal its per_core_throughput (`total_evals / wall_clock_seconds / cpu_cores`) divided by the median of all per_core_throughputs across all entries, formatted to 1 decimal place. When the file contains only one entry, the Factor SHALL be 1.0.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6**
