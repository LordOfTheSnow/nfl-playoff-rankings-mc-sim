"""Tests for src/experience_export.py — solver performance export module."""

from unittest.mock import patch, MagicMock
import logging

import pytest

from src.experience_export import (
    SolverPerformanceEntry,
    format_table_row,
    get_cpu_info,
    _compute_factors,
    _parse_and_insert_row,
    export_solver_performance,
    _FILE_HEADER,
    _TABLE_HEADER,
    _TABLE_SEPARATOR,
)
from src.clinching import ClinchingResult


# --- SolverPerformanceEntry dataclass construction ---


class TestSolverPerformanceEntry:
    def test_construction_with_all_fields(self):
        entry = SolverPerformanceEntry(
            cpu_model="Intel(R) Core(TM) i7-10700K",
            cpu_cores=8,
            relevant_games_count=12,
            wall_clock_seconds=3.47,
            method="enumeration",
            total_evals=531441,
        )
        assert entry.cpu_model == "Intel(R) Core(TM) i7-10700K"
        assert entry.cpu_cores == 8
        assert entry.relevant_games_count == 12
        assert entry.wall_clock_seconds == 3.47
        assert entry.method == "enumeration"
        assert entry.total_evals == 531441


# --- format_table_row() ---


class TestFormatTableRow:
    def test_output_is_pipe_delimited(self):
        entry = SolverPerformanceEntry(
            cpu_model="Apple M1",
            cpu_cores=4,
            relevant_games_count=9,
            wall_clock_seconds=1.23,
            method="enumeration",
            total_evals=19683,
        )
        row = format_table_row(entry, factor=1.5)
        assert row.startswith("| ")
        assert row.endswith("|\n")

    def test_field_order(self):
        entry = SolverPerformanceEntry(
            cpu_model="TestCPU",
            cpu_cores=16,
            relevant_games_count=14,
            wall_clock_seconds=8.92,
            method="sampling",
            total_evals=10000,
        )
        row = format_table_row(entry, factor=0.3)
        parts = [p.strip() for p in row.split("|")]
        # parts[0] is empty (before first |), parts[-1] is empty or \n
        data_parts = [p for p in parts if p]
        assert data_parts[0] == "TestCPU"
        assert data_parts[1] == "16"
        assert data_parts[2] == "14"
        assert data_parts[3] == "8.92"
        assert data_parts[4] == "sampling"
        assert data_parts[5] == "10000"
        assert data_parts[6] == "0.3"

    def test_wall_clock_two_decimal_places(self):
        entry = SolverPerformanceEntry(
            cpu_model="CPU",
            cpu_cores=4,
            relevant_games_count=5,
            wall_clock_seconds=3.1,
            method="enumeration",
            total_evals=100,
        )
        row = format_table_row(entry, factor=1.0)
        assert "3.10" in row

    def test_factor_one_decimal_place(self):
        entry = SolverPerformanceEntry(
            cpu_model="CPU",
            cpu_cores=4,
            relevant_games_count=5,
            wall_clock_seconds=3.47,
            method="enumeration",
            total_evals=100,
        )
        row = format_table_row(entry, factor=2.345)
        # Factor should be formatted to 1 decimal place: 2.3
        parts = [p.strip() for p in row.split("|")]
        data_parts = [p for p in parts if p]
        assert data_parts[6] == "2.3"

    def test_factor_appears_as_last_column(self):
        entry = SolverPerformanceEntry(
            cpu_model="CPU",
            cpu_cores=4,
            relevant_games_count=5,
            wall_clock_seconds=1.00,
            method="enumeration",
            total_evals=200,
        )
        row = format_table_row(entry, factor=0.7)
        # The last data column before the closing | should be the factor
        parts = [p.strip() for p in row.strip().split("|")]
        non_empty = [p for p in parts if p]
        assert non_empty[-1] == "0.7"


# --- get_cpu_info() ---


class TestGetCpuInfo:
    def test_return_type_is_tuple(self):
        result = get_cpu_info()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], str)

    @patch("src.experience_export.os.cpu_count", return_value=None)
    @patch("src.experience_export._read_cpuinfo_model", return_value="SomeCPU")
    def test_cpu_count_none_returns_zero(self, mock_cpuinfo, mock_count):
        cores, _ = get_cpu_info()
        assert cores == 0

    @patch("src.experience_export.os.cpu_count", return_value=8)
    @patch("src.experience_export._read_cpuinfo_model", return_value="SomeCPU")
    def test_cpu_count_returns_value(self, mock_cpuinfo, mock_count):
        cores, _ = get_cpu_info()
        assert cores == 8

    @patch("src.experience_export.platform.processor", return_value="")
    @patch("src.experience_export._read_cpuinfo_model", return_value="Unknown")
    @patch("src.experience_export.os.cpu_count", return_value=4)
    def test_fallback_to_unknown(self, mock_count, mock_cpuinfo, mock_processor):
        """When both /proc/cpuinfo and platform.processor() fail, returns 'Unknown'."""
        _, model = get_cpu_info()
        assert model == "Unknown"

    @patch("src.experience_export.platform.processor", return_value="x86_64")
    @patch("src.experience_export._read_cpuinfo_model", return_value="Unknown")
    @patch("src.experience_export.os.cpu_count", return_value=8)
    def test_skips_generic_arch_string(self, mock_count, mock_cpuinfo, mock_proc):
        """platform.processor() returning 'x86_64' is treated as non-informative."""
        _, model = get_cpu_info()
        assert model == "Unknown"

    @patch("src.experience_export.platform.processor", return_value="Apple M1 Pro")
    @patch("src.experience_export._read_cpuinfo_model", return_value="Unknown")
    @patch("src.experience_export.os.cpu_count", return_value=10)
    def test_uses_platform_processor_when_cpuinfo_unavailable(self, mock_count, mock_cpuinfo, mock_proc):
        """Falls back to platform.processor() when /proc/cpuinfo not available (e.g. macOS)."""
        _, model = get_cpu_info()
        assert model == "Apple M1 Pro"

    @patch("src.experience_export._read_cpuinfo_model", return_value="AMD Ryzen 9 5950X")
    @patch("src.experience_export.os.cpu_count", return_value=16)
    def test_prefers_proc_cpuinfo(self, mock_count, mock_cpuinfo):
        """Prefers /proc/cpuinfo over platform.processor() (Linux)."""
        _, model = get_cpu_info()
        assert model == "AMD Ryzen 9 5950X"


# --- _compute_factors() ---


class TestComputeFactors:
    def test_single_entry_returns_one(self):
        result = _compute_factors([(8, 2.0, 1000, "CPU-A", 9)])
        assert result == [1.0]

    def test_same_hardware_all_get_factor_one(self):
        # All entries from the same hardware -> all get factor 1.0
        # regardless of different throughputs (workload sizes differ)
        result = _compute_factors([
            (4, 2.0, 800, "CPU-A", 9),
            (4, 1.0, 800, "CPU-A", 5),
            (4, 4.0, 800, "CPU-A", 14),
        ])
        assert all(f == 1.0 for f in result)

    def test_different_hardware_produces_different_factors(self):
        # CPU-A: cores=4, wall=2.0, evals=800 -> throughput = 100/core
        # CPU-B: cores=8, wall=1.0, evals=1600 -> throughput = 200/core
        # Group averages: A=100, B=200, median=150
        # Factor A = 100/150 ≈ 0.67, Factor B = 200/150 ≈ 1.33
        result = _compute_factors([
            (4, 2.0, 800, "CPU-A", 9),
            (8, 1.0, 1600, "CPU-B", 9),
        ])
        assert len(result) == 2
        assert result[0] == pytest.approx(100.0 / 150.0, rel=0.01)
        assert result[1] == pytest.approx(200.0 / 150.0, rel=0.01)

    def test_all_rows_in_same_group_share_factor(self):
        # Two rows from CPU-A, one from CPU-B
        # CPU-A rows: throughput 100, 200 -> avg = 150
        # CPU-B rows: throughput 300 -> avg = 300
        # Median of group avgs = median(150, 300) = 225
        # Factor A = 150/225 ≈ 0.67, Factor B = 300/225 ≈ 1.33
        result = _compute_factors([
            (4, 2.0, 800, "CPU-A", 9),    # throughput = 100
            (4, 1.0, 800, "CPU-A", 5),    # throughput = 200
            (8, 1.0, 2400, "CPU-B", 9),   # throughput = 300
        ])
        assert len(result) == 3
        # Both CPU-A rows share the same factor
        assert result[0] == result[1]
        # CPU-B has higher factor
        assert result[2] > result[0]

    def test_empty_list_returns_empty(self):
        result = _compute_factors([])
        assert result == []


# --- _parse_and_insert_row() ---


class TestParseAndInsertRow:
    def _build_file_content(self, data_rows: list[str]) -> str:
        content = _FILE_HEADER + _TABLE_HEADER + _TABLE_SEPARATOR
        for row in data_rows:
            content += row + "\n"
        return content

    def test_insert_into_existing_group(self):
        existing = self._build_file_content([
            "| Intel i7 | 8 | 12 | 3.47 | enumeration | 531441 | 1.0 |",
        ])
        new_row = "| Intel i7 | 8 | 9 | 1.82 | enumeration | 19683 | 1.0 |\n"
        result = _parse_and_insert_row(existing, new_row, "Intel i7", 8)
        lines = [l for l in result.split("\n") if l.startswith("| ") and "---" not in l and "CPU Model" not in l]
        assert len(lines) == 2
        # Both rows should have cpu_model "Intel i7" and cores 8
        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            non_empty = [p for p in parts if p]
            assert non_empty[0] == "Intel i7"
            assert non_empty[1] == "8"

    def test_new_group_when_no_match(self):
        existing = self._build_file_content([
            "| Intel i7 | 8 | 12 | 3.47 | enumeration | 531441 | 1.0 |",
        ])
        new_row = "| Apple M1 | 4 | 9 | 1.23 | enumeration | 19683 | 1.0 |\n"
        result = _parse_and_insert_row(existing, new_row, "Apple M1", 4)
        lines = [l for l in result.split("\n") if l.startswith("| ") and "---" not in l and "CPU Model" not in l]
        assert len(lines) == 2
        # New group row should be at the end
        last_row_parts = [p.strip() for p in lines[-1].split("|")]
        non_empty = [p for p in last_row_parts if p]
        assert non_empty[0] == "Apple M1"

    def test_preserves_all_existing_rows(self):
        existing_rows = [
            "| Intel i7 | 8 | 12 | 3.47 | enumeration | 531441 | 1.0 |",
            "| Apple M1 | 4 | 9 | 1.23 | enumeration | 19683 | 1.5 |",
        ]
        existing = self._build_file_content(existing_rows)
        new_row = "| Intel i7 | 8 | 14 | 5.00 | sampling | 10000 | 1.0 |\n"
        result = _parse_and_insert_row(existing, new_row, "Intel i7", 8)
        data_lines = [l for l in result.split("\n") if l.startswith("| ") and "---" not in l and "CPU Model" not in l]
        # Should have 3 rows total (2 existing + 1 new)
        assert len(data_lines) == 3
        # Verify the first six columns of original rows are preserved
        for row in existing_rows:
            original_cols = [p.strip() for p in row.split("|")][1:7]  # first 6 data cols
            found = False
            for line in data_lines:
                line_cols = [p.strip() for p in line.split("|")][1:7]
                if line_cols == original_cols:
                    found = True
                    break
            assert found, f"Original row columns not preserved: {original_cols}"

    def test_recalculates_factor_for_all_rows(self):
        # Single existing row has factor 1.0. After adding a new row, factors
        # should be recalculated based on the new median.
        existing = self._build_file_content([
            "| Intel i7 | 8 | 12 | 2.00 | enumeration | 800 | 1.0 |",
        ])
        # New row: cores=4, wall=1.0, evals=800 -> throughput = 200
        # Existing: cores=8, wall=2.0, evals=800 -> throughput = 50
        # Median = 125, factors = [50/125, 200/125] = [0.4, 1.6]
        new_row = "| Apple M1 | 4 | 9 | 1.00 | enumeration | 800 | 1.0 |\n"
        result = _parse_and_insert_row(existing, new_row, "Apple M1", 4)
        data_lines = [l for l in result.split("\n") if l.startswith("| ") and "---" not in l and "CPU Model" not in l]
        assert len(data_lines) == 2
        # Verify factor column is no longer 1.0 for both rows
        factors = []
        for line in data_lines:
            parts = [p.strip() for p in line.split("|")]
            non_empty = [p for p in parts if p]
            factors.append(float(non_empty[6]))
        # Neither factor should be 1.0 since throughputs differ
        assert factors[0] != 1.0 or factors[1] != 1.0

    def test_handles_malformed_rows_gracefully(self):
        # Malformed row with missing columns
        existing = self._build_file_content([
            "| Intel i7 | 8 | 12 | 3.47 | enumeration | 531441 | 1.0 |",
            "| bad row missing columns |",
        ])
        new_row = "| Apple M1 | 4 | 9 | 1.23 | enumeration | 19683 | 1.0 |\n"
        # Should not raise an exception
        result = _parse_and_insert_row(existing, new_row, "Apple M1", 4)
        assert result is not None
        assert len(result) > 0

    def test_handles_non_integer_cores_gracefully(self):
        existing = self._build_file_content([
            "| Intel i7 | notanint | 12 | 3.47 | enumeration | 531441 | 1.0 |",
        ])
        new_row = "| Apple M1 | 4 | 9 | 1.23 | enumeration | 19683 | 1.0 |\n"
        # Should not raise an exception
        result = _parse_and_insert_row(existing, new_row, "Apple M1", 4)
        assert result is not None


# --- export_solver_performance() ---


class TestExportSolverPerformance:
    def _make_result(self, error=None) -> ClinchingResult:
        return ClinchingResult(
            team="Bills",
            method="enumeration",
            exhaustive=True,
            relevant_games_count=12,
            total_evals=531441,
            error=error,
        )

    @patch("src.experience_export.get_cpu_info", return_value=(8, "Intel i7"))
    def test_file_creation_with_header_structure(self, mock_cpu, tmp_path):
        output_file = tmp_path / "solver-performance.md"
        result = self._make_result()
        export_solver_performance(result, 3.47, output_path=str(output_file))
        content = output_file.read_text()
        assert content.startswith("# Solver Performance\n\n")
        assert "| CPU Model | CPU Cores | Relevant Games | Wall Clock (s) | Method | Total Evals | Factor |" in content
        assert "| --- | --- | --- | --- | --- | --- | --- |" in content
        # Verify data row exists
        data_lines = [l for l in content.split("\n") if l.startswith("| ") and "---" not in l and "CPU Model" not in l]
        assert len(data_lines) == 1

    @patch("src.experience_export.get_cpu_info", return_value=(8, "Intel i7"))
    def test_grouping_insertion_when_file_exists(self, mock_cpu, tmp_path):
        output_file = tmp_path / "solver-performance.md"
        result = self._make_result()
        # First write
        export_solver_performance(result, 3.47, output_path=str(output_file))
        # Second write with same CPU
        export_solver_performance(result, 1.82, output_path=str(output_file))
        content = output_file.read_text()
        data_lines = [l for l in content.split("\n") if l.startswith("| ") and "---" not in l and "CPU Model" not in l]
        assert len(data_lines) == 2

    def test_skip_on_error_result(self, tmp_path):
        output_file = tmp_path / "solver-performance.md"
        result = self._make_result(error="Something went wrong")
        export_solver_performance(result, 3.47, output_path=str(output_file))
        assert not output_file.exists()

    @patch("src.experience_export.get_cpu_info", return_value=(8, "Intel i7"))
    def test_graceful_io_error_handling(self, mock_cpu, tmp_path, caplog):
        result = self._make_result()
        # Use a path that will cause an OSError (e.g., writing to a file in a
        # read-only location)
        with patch("src.experience_export.Path.exists", return_value=False):
            with patch(
                "src.experience_export.Path.parent",
                new_callable=lambda: property(lambda self: MagicMock()),
            ):
                with patch("builtins.open", side_effect=OSError("Permission denied")):
                    with caplog.at_level(logging.WARNING):
                        # Should not raise
                        export_solver_performance(
                            result, 3.47, output_path="/nonexistent/path/file.md"
                        )

    @patch("src.experience_export.get_cpu_info", return_value=(8, "Intel i7"))
    def test_parent_directory_creation(self, mock_cpu, tmp_path):
        output_file = tmp_path / "subdir" / "nested" / "solver-performance.md"
        result = self._make_result()
        export_solver_performance(result, 3.47, output_path=str(output_file))
        assert output_file.exists()
        assert output_file.parent.exists()
