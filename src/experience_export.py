"""Solver performance export module.

Exports solver performance data to a markdown table file.
"""

import logging
import os
import platform
import statistics
from dataclasses import dataclass
from pathlib import Path

from src.clinching import ClinchingResult

logger = logging.getLogger("src.experience_export")

# Generic architecture strings that platform.processor() may return on Linux.
# These are not useful as CPU model identifiers.
_GENERIC_ARCH_STRINGS = frozenset({"x86_64", "aarch64", "arm", "i386", "i686", "AMD64"})


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


_FILE_HEADER = "# Solver Performance\n\n"
_TABLE_HEADER = "| CPU Model | CPU Cores | Relevant Games | Wall Clock (s) | Method | Total Evals | Factor |\n"
_TABLE_SEPARATOR = "| --- | ---: | ---: | ---: | --- | ---: | ---: |\n"


def get_cpu_info() -> tuple[int, str]:
    """Return (cpu_cores, cpu_model) with fallback logic.

    - cpu_cores: os.cpu_count() or 0 if None
    - cpu_model: /proc/cpuinfo first (most specific on Linux), falling back
      to platform.processor() (if informative), falling back to "Unknown"

    Note: platform.processor() often returns just the architecture (e.g.
    "x86_64") on Linux, which is not useful. We prefer /proc/cpuinfo which
    has the full model name (e.g. "12th Gen Intel(R) Core(TM) i5-1245U").
    """
    cpu_cores = os.cpu_count() or 0

    # Try /proc/cpuinfo first — it has the detailed model on Linux
    cpu_model = _read_cpuinfo_model()
    if cpu_model == "Unknown":
        # Try sysctl on macOS
        cpu_model = _read_sysctl_cpu_model()
    if cpu_model == "Unknown":
        # Fall back to platform.processor(), but skip generic arch strings
        proc = platform.processor()
        if proc and proc not in _GENERIC_ARCH_STRINGS:
            cpu_model = proc

    return cpu_cores, cpu_model


def _read_cpuinfo_model() -> str:
    """Read CPU model from /proc/cpuinfo (Linux). Returns 'Unknown' on failure."""
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


def _read_sysctl_cpu_model() -> str:
    """Read CPU model via sysctl (macOS). Returns 'Unknown' on failure."""
    import subprocess
    try:
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "Unknown"


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


def _compute_factors(rows_data: list[tuple[int, float, int, str, int]]) -> list[float]:
    """Compute performance factors grouped by hardware.

    The factor compares hardware performance, not workload size. All rows
    from the same (cpu_model, cpu_cores) get the same factor — their average
    throughput relative to the global median across all hardware groups.

    This means factor=1.0 when there's only one type of hardware. When you
    have results from multiple machines, faster hardware gets factor > 1.0
    and slower hardware gets factor < 1.0.

    Args:
        rows_data: List of (cpu_cores, wall_clock_seconds, total_evals,
                   cpu_model, relevant_games) for each row.

    Returns:
        List of factor values for each row. All rows from the same hardware
        group share the same factor.
    """
    if not rows_data:
        return []

    # Group rows by hardware (cpu_model, cpu_cores)
    from collections import defaultdict
    groups: dict[tuple[str, int], list[int]] = defaultdict(list)
    for i, (cpu_cores, wall_clock, total_evals, cpu_model, _) in enumerate(rows_data):
        groups[(cpu_model, cpu_cores)].append(i)

    # If only one hardware group, all factors are 1.0
    if len(groups) <= 1:
        return [1.0] * len(rows_data)

    # Compute average per-core throughput for each hardware group
    group_throughputs: dict[tuple[str, int], float] = {}
    for key, indices in groups.items():
        throughputs = []
        for i in indices:
            cpu_cores, wall_clock, total_evals, _, _ = rows_data[i]
            if cpu_cores > 0 and wall_clock > 0.0:
                throughputs.append(total_evals / wall_clock / cpu_cores)
        group_throughputs[key] = (
            statistics.mean(throughputs) if throughputs else 0.0
        )

    # Median of group averages
    avg_values = [v for v in group_throughputs.values() if v > 0.0]
    if not avg_values:
        return [1.0] * len(rows_data)
    median_throughput = statistics.median(avg_values)

    if median_throughput == 0.0:
        return [1.0] * len(rows_data)

    # Assign factor per hardware group
    group_factors: dict[tuple[str, int], float] = {
        key: (tp / median_throughput if tp > 0.0 else 0.0)
        for key, tp in group_throughputs.items()
    }

    # Map back to individual rows
    factors = [1.0] * len(rows_data)
    for key, indices in groups.items():
        f = group_factors[key]
        for i in indices:
            factors[i] = f

    return factors


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
    rows_data: list[tuple[int, float, int, str, int]] = []
    for row in all_rows:
        cols = [c.strip() for c in row.split("|")]
        # cols[1] = CPU Model, cols[2] = CPU Cores, cols[3] = Relevant Games,
        # cols[4] = Wall Clock (s), cols[6] = Total Evals
        try:
            r_model = cols[1]
            r_cores = int(cols[2])
            r_games = int(cols[3])
            r_wall = float(cols[4])
            r_evals = int(cols[6])
        except (ValueError, IndexError):
            r_model, r_cores, r_games, r_wall, r_evals = "", 0, 0, 0.0, 0
        rows_data.append((r_cores, r_wall, r_evals, r_model, r_games))

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



def generate_solver_performance_markdown(timings: list[dict]) -> str:
    """Generate solver-performance.md content from stored timing data.

    Builds the markdown table from timing records (from cache) plus
    the current machine's CPU info. Each timing entry becomes a row.

    Args:
        timings: List of dicts with keys: ms_per_eval, method,
                 relevant_games_count, total_evals, recorded_at.

    Returns:
        Full markdown file content ready for download.
    """
    if not timings:
        return _FILE_HEADER + _TABLE_HEADER + _TABLE_SEPARATOR

    cpu_cores, cpu_model = get_cpu_info()

    # Build entries from timing data
    entries: list[SolverPerformanceEntry] = []
    for t in timings:
        # Derive wall_clock_seconds from ms_per_eval and total_evals
        total_evals = t.get("total_evals", 0)
        ms_per_eval = t.get("ms_per_eval", 0.0)
        wall_clock = (ms_per_eval * total_evals) / 1000.0 if total_evals > 0 else 0.0

        entries.append(SolverPerformanceEntry(
            cpu_model=cpu_model,
            cpu_cores=cpu_cores,
            relevant_games_count=t.get("relevant_games_count", 0),
            wall_clock_seconds=wall_clock,
            method=t.get("method", "unknown"),
            total_evals=total_evals,
        ))

    # Compute factors across all entries
    rows_data = [
        (e.cpu_cores, e.wall_clock_seconds, e.total_evals, e.cpu_model, e.relevant_games_count)
        for e in entries
    ]
    factors = _compute_factors(rows_data)

    # Build the file content
    result = _FILE_HEADER + _TABLE_HEADER + _TABLE_SEPARATOR
    for entry, factor in zip(entries, factors):
        result += format_table_row(entry, factor)

    return result


def export_timings_to_file(timings: list[dict], output_path: str) -> int:
    """Export timing data to a project-local markdown file, compacted by hardware+method.

    Groups all timing measurements by (CPU Model, CPU Cores, Method) and writes
    one row per group using the median wall clock and median total evals. This
    keeps the file compact while accumulating cross-platform results.

    Preserves existing rows from other platforms (read from the file). Replaces
    the row for the current platform+method if it already exists (updated median).

    Args:
        timings: List of timing dicts from cache (ms_per_eval, method,
                 relevant_games_count, total_evals, recorded_at).
        output_path: Path to the output file (e.g. "doc/solver-performance.md").

    Returns:
        Number of rows written for the current platform.
    """
    from collections import defaultdict

    cpu_cores, cpu_model = get_cpu_info()
    path = Path(output_path)

    if not timings:
        return 0

    # Group timings by (method, num_workers) and compute medians
    method_worker_groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for t in timings:
        workers = t.get("num_workers", 0) or cpu_cores  # fallback for old records
        method_worker_groups[(t.get("method", "unknown"), workers)].append(t)

    # Build one compacted entry per (method, num_workers) for the current hardware
    current_entries: list[SolverPerformanceEntry] = []
    for (method, workers), group in method_worker_groups.items():
        wall_clocks = []
        total_evals_list = []
        relevant_games_list = []
        for t in group:
            evals = t.get("total_evals", 0)
            ms_per = t.get("ms_per_eval", 0.0)
            wall_clocks.append((ms_per * evals) / 1000.0 if evals > 0 else 0.0)
            total_evals_list.append(evals)
            relevant_games_list.append(t.get("relevant_games_count", 0))

        current_entries.append(SolverPerformanceEntry(
            cpu_model=cpu_model,
            cpu_cores=workers,
            relevant_games_count=int(statistics.median(relevant_games_list)),
            wall_clock_seconds=round(statistics.median(wall_clocks), 2),
            method=method,
            total_evals=int(statistics.median(total_evals_list)),
        ))

    if not current_entries:
        return 0

    # Ensure parent directory exists
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing file and parse rows from OTHER platforms
    other_entries: list[SolverPerformanceEntry] = []
    if path.exists():
        existing_content = path.read_text()
        for line in existing_content.split("\n"):
            if line.startswith("| ") and "---" not in line and "CPU Model" not in line:
                cols = [c.strip() for c in line.split("|")]
                if len(cols) >= 8:
                    try:
                        row_model = cols[1]
                        row_cores = int(cols[2])
                        # Skip rows from the current platform (we're replacing them)
                        if row_model == cpu_model:
                            continue
                        other_entries.append(SolverPerformanceEntry(
                            cpu_model=row_model,
                            cpu_cores=row_cores,
                            relevant_games_count=int(cols[3]),
                            wall_clock_seconds=float(cols[4]),
                            method=cols[5],
                            total_evals=int(cols[6]),
                        ))
                    except (ValueError, IndexError):
                        continue

    # Combine: other platforms + current platform entries
    all_entries = other_entries + current_entries

    # Compute factors across all entries
    rows_data = [
        (e.cpu_cores, e.wall_clock_seconds, e.total_evals, e.cpu_model, e.relevant_games_count)
        for e in all_entries
    ]
    factors = _compute_factors(rows_data)

    # Sort by factor (ascending), then by cpu_model+cores to group same hardware
    paired = list(zip(all_entries, factors))
    paired.sort(key=lambda ef: (ef[1], ef[0].cpu_model, ef[0].cpu_cores))

    # Write the file
    content = _FILE_HEADER + _TABLE_HEADER + _TABLE_SEPARATOR
    for entry, factor in paired:
        content += format_table_row(entry, factor)

    path.write_text(content)
    return len(current_entries)


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
