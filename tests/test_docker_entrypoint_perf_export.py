"""Tests for docker-entrypoint.py --perf-export-path injection.

Validates that resolve_config() correctly injects --perf-export-path
/data/doc/solver-performance.md following the same pattern as --db-path.

Requirements: 7.2, 7.6
"""

from __future__ import annotations

import importlib

import pytest

# Import from hyphenated filename using importlib
docker_entrypoint = importlib.import_module("docker-entrypoint")
resolve_config = docker_entrypoint.resolve_config


class TestPerfExportPathInjection:
    """Tests for --perf-export-path injection in resolve_config()."""

    def test_injects_perf_export_path_when_absent(self) -> None:
        """resolve_config() injects --perf-export-path when not in CMD args."""
        env_vars = {"SEASON": "2024"}
        cmd_args: list[str] = []

        result = resolve_config(env_vars, cmd_args)

        assert "--perf-export-path" in result
        idx = result.index("--perf-export-path")
        assert result[idx + 1] == "/data/doc/solver-performance.md"

    def test_does_not_inject_when_already_present(self) -> None:
        """resolve_config() does NOT inject --perf-export-path when already in CMD args."""
        env_vars = {"SEASON": "2024"}
        cmd_args = ["--perf-export-path", "/custom/path.md"]

        result = resolve_config(env_vars, cmd_args)

        # Should only appear once (the user-provided one via cmd_args passthrough)
        count = result.count("--perf-export-path")
        assert count == 1

    def test_preserves_user_provided_value(self) -> None:
        """resolve_config() preserves user-provided --perf-export-path value."""
        env_vars = {"SEASON": "2024"}
        custom_path = "/my/custom/solver-perf.md"
        cmd_args = ["--perf-export-path", custom_path]

        result = resolve_config(env_vars, cmd_args)

        idx = result.index("--perf-export-path")
        assert result[idx + 1] == custom_path

    def test_injection_appears_before_cmd_overrides(self) -> None:
        """--perf-export-path injection appears before CMD overrides in output."""
        env_vars = {"SEASON": "2024"}
        cmd_args = ["--some-other-flag", "value"]

        result = resolve_config(env_vars, cmd_args)

        perf_idx = result.index("--perf-export-path")
        other_idx = result.index("--some-other-flag")
        assert perf_idx < other_idx, (
            "--perf-export-path should appear before CMD overrides"
        )
