# Implementation Plan: Docker Containerization

## Overview

Add optional Docker support to the NFL Monte Carlo Playoff Simulator. The implementation adds a multi-stage Dockerfile, an entrypoint script that bridges environment variables to CLI arguments, a Docker Compose file for single-command startup, and a `--db-path` CLI argument to the server for container-friendly database paths.

## Tasks

- [x] 1. Add `--db-path` CLI argument to the server
  - [x] 1.1 Add `--db-path` argument to `parse_args()` in `src/server.py`
    - Add `--db-path` argument with default `"nfl_cache.db"` to preserve existing behavior
    - Pass `args.db_path` to `Cache(db_path=...)` in the `main()` function
    - _Requirements: 3.1, 4.1_

  - [ ]* 1.2 Write unit tests for `--db-path` argument
    - Test that `parse_args(["--db-path", "/data/nfl_cache.db"])` sets `db_path` correctly
    - Test default value remains `"nfl_cache.db"` when argument is omitted
    - _Requirements: 3.1_

- [x] 2. Implement `docker-entrypoint.py` with env var validation and CLI precedence logic
  - [x] 2.1 Create `docker-entrypoint.py` in project root
    - Implement `resolve_config(env_vars: dict, cmd_args: list[str])` as a pure, testable function
    - Read `PORT` and `SEASON` from environment variables
    - Validate `PORT` is an integer in range 1–65535 (exit code 1 with descriptive error on failure)
    - Validate `SEASON` is an integer in range 2000–2100 (exit code 1 with descriptive error on failure)
    - Apply precedence: CLI args from CMD override env vars
    - Always inject `--static-dir /app/frontend` and `--db-path /data/nfl_cache.db`
    - Always inject `--host 0.0.0.0` for container networking
    - Use `os.execvp` to replace PID 1 with the application process
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.1, 5.1_

  - [ ]* 2.2 Write property test for port resolution precedence
    - **Property 1: Port resolution precedence**
    - Generate valid port values (1–65535) as env var and optional `--port` CLI override
    - Assert resolved port equals CLI value when present, env value otherwise, 8080 when neither
    - **Validates: Requirements 2.2, 2.3, 2.5, 2.9**

  - [ ]* 2.3 Write property test for season resolution precedence
    - **Property 2: Season resolution precedence**
    - Generate valid season values (2000–2100) as env var and optional `--season` CLI override
    - Assert resolved season equals CLI value when present, env value otherwise
    - **Validates: Requirements 2.2, 2.4, 2.6**

  - [ ]* 2.4 Write property test for invalid PORT rejection
    - **Property 3: Invalid PORT rejection**
    - Generate strings that are NOT valid integers in 1–65535 (non-numeric, negative, zero, >65535, floats)
    - Assert entrypoint exits with non-zero code and error message contains the invalid value
    - **Validates: Requirements 2.7**

  - [ ]* 2.5 Write property test for invalid SEASON rejection
    - **Property 4: Invalid SEASON rejection**
    - Generate strings that are NOT valid integers in 2000–2100 (non-numeric, <2000, >2100, floats)
    - Assert entrypoint exits with non-zero code and error message contains the invalid value
    - **Validates: Requirements 2.8**

- [x] 3. Checkpoint - Verify entrypoint logic
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Create Dockerfile with multi-stage build
  - [x] 4.1 Create `Dockerfile` in project root
    - Stage 1 (builder): use `python:3.14-slim`, copy `pyproject.toml` and `src/`, run `pip install .`
    - Stage 2 (runtime): use `python:3.14-slim`, copy installed packages from builder, copy `src/`, `frontend/`, and `docker-entrypoint.py`
    - Create `/data` directory with appropriate permissions
    - Set `WORKDIR /app`, `EXPOSE 8080`
    - Set `ENTRYPOINT ["python", "docker-entrypoint.py"]`
    - Ensure final image excludes dev dependencies (pytest, hypothesis)
    - Target final image size under 200 MB uncompressed
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 5.1, 5.2_

- [x] 5. Create `.dockerignore` file
  - [x] 5.1 Create `.dockerignore` in project root
    - Exclude: `.venv/`, `.git/`, `__pycache__/`, `.hypothesis/`, `.pytest_cache/`, `.playwright-mcp/`, `nfl_cache.db`, `tests/`, `*.pyc`, `.env`
    - _Requirements: 1.7, 7.1_

- [x] 6. Create `compose.yaml`
  - [x] 6.1 Create `compose.yaml` in project root
    - Define `simulator` service with `build: .`
    - Map ports using variable interpolation: `"${PORT:-8080}:8080"`
    - Pass environment variables: `PORT=${PORT:-}`, `SEASON=${SEASON:-}`
    - Declare named volume `nfl-data` mounted to `/data`
    - Set `shm_size: "64m"` for multiprocessing support
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 5.4_

- [x] 7. Update README with Docker documentation
  - [x] 7.1 Add Docker section to `README.md`
    - State that Docker is optional and existing pip-based workflow remains fully supported
    - Provide runnable command example for building the image
    - Provide runnable command example for running with a bind mount
    - Provide runnable command example for running with a named volume
    - Provide runnable command example for configuring `PORT` and `SEASON` env vars
    - Provide runnable command example for starting via Docker Compose
    - _Requirements: 7.2, 7.3_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The `docker-entrypoint.py` script's `resolve_config()` function is extracted as pure logic for testability
- Integration/Docker-based tests (image size, container startup, volume persistence) are out of scope for automated task execution — they require a Docker daemon

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "5.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5"] },
    { "id": 3, "tasks": ["4.1", "6.1"] },
    { "id": 4, "tasks": ["7.1"] }
  ]
}
```
