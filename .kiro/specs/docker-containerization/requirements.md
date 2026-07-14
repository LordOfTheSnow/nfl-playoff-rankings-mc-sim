# Requirements Document

## Introduction

This feature adds optional Docker containerization support to the NFL Monte Carlo Playoff Simulator. Users who prefer Docker can build and run the application in an isolated container, while the existing bare-metal workflow remains unchanged. The SQLite database file used for caching ESPN API responses can be persisted across container restarts via bind mounts or Docker named volumes.

## Glossary

- **Container_Image**: A Docker image built from the project's Dockerfile that packages the application, its Python runtime, and all dependencies into an immutable artifact.
- **Container**: A running instance of the Container_Image that serves the NFL simulator web application.
- **Bind_Mount**: A Docker host-path mount that maps a file or directory on the host filesystem into the container, allowing data to persist outside the container lifecycle.
- **Volume_Mount**: A Docker named volume that stores data in a Docker-managed location on the host, independent of the container lifecycle.
- **Database_File**: The SQLite database file (`nfl_cache.db`) used by the Cache module to persist ESPN API responses.
- **Dockerfile**: A build recipe in the project root that defines how to construct the Container_Image.
- **Build_System**: The Docker build tooling (`docker build`) that produces the Container_Image from the Dockerfile.

## Requirements

### Requirement 1: Container Image Build

**User Story:** As a developer, I want to build a Docker image of the simulator, so that I can run the application in an isolated, reproducible environment.

#### Acceptance Criteria

1. THE Dockerfile SHALL be located in the project root directory
2. WHEN a user runs `docker build` in the project root, THE Build_System SHALL produce a Container_Image containing the Python 3.11+ runtime, the application source code, the frontend static files, and the httpx dependency
3. THE Container_Image SHALL use a multi-stage or minimal base image such that the final image size does not exceed 200 MB uncompressed
4. THE Dockerfile SHALL not include development dependencies (pytest, hypothesis) in the final Container_Image
5. THE Container_Image SHALL set the application entry point to `python -m src` so that the Container starts the web server by default
6. THE Container_Image SHALL expose port 8080 so that the web server is accessible from outside the container
7. THE project SHALL include a .dockerignore file that excludes at minimum the .venv directory, the .git directory, and the tests directory from the build context

### Requirement 2: Container Runtime Configuration

**User Story:** As a user, I want to configure the containerized application via standard Docker mechanisms, so that I can customize the port, season, and other settings without rebuilding the image.

#### Acceptance Criteria

1. THE Container SHALL expose port 8080 as the default listening port via a Dockerfile `EXPOSE 8080` directive
2. WHEN a user passes `--port`, `--season`, or `--static-dir` arguments via Docker CMD override, THE Container SHALL forward those arguments to the application entry point (`python -m src`)
3. THE Container SHALL read the `PORT` environment variable and, if set, use its integer value (in the range 1–65535) as the application listening port when no `--port` CLI argument is provided
4. THE Container SHALL read the `SEASON` environment variable and, if set, use its four-digit integer value (in the range 2000–2100) as the NFL season year when no `--season` CLI argument is provided
5. WHEN both the `PORT` environment variable and the `--port` CLI argument are provided, THE Container SHALL use the `--port` CLI argument value and ignore the `PORT` environment variable
6. WHEN both the `SEASON` environment variable and the `--season` CLI argument are provided, THE Container SHALL use the `--season` CLI argument value and ignore the `SEASON` environment variable
7. IF the `PORT` environment variable is set to a value that is not an integer in the range 1–65535, THEN THE Container SHALL exit with a non-zero exit code and output an error message indicating the invalid port value
8. IF the `SEASON` environment variable is set to a value that is not a four-digit integer in the range 2000–2100, THEN THE Container SHALL exit with a non-zero exit code and output an error message indicating the invalid season value
9. WHEN neither the `PORT` environment variable nor the `--port` CLI argument is provided, THE Container SHALL default to listening on port 8080

### Requirement 3: Database Persistence via Bind Mount

**User Story:** As a user, I want to mount the SQLite database from my host filesystem into the container, so that cached data survives container restarts and I can inspect the database locally.

#### Acceptance Criteria

1. THE Container_Image SHALL include a `/data` directory and THE Container SHALL store the Database_File at `/data/nfl_cache.db`
2. WHEN a user specifies a bind mount mapping a host path to `/data/nfl_cache.db`, THE Container SHALL read from and write to the host file so that data written in one container session is available in subsequent sessions using the same mount
3. IF no mount is provided for `/data/nfl_cache.db`, THEN THE Container SHALL create a new Database_File at `/data/nfl_cache.db` and data SHALL NOT persist after the container is removed
4. IF the mounted host file does not exist, THEN THE Container SHALL create a new empty Database_File at the mount path
5. IF the Container process cannot write to the mounted path due to filesystem permissions, THEN THE Container SHALL exit with a non-zero exit code and emit a log message indicating the write failure

### Requirement 4: Database Persistence via Named Volume

**User Story:** As a user, I want to use a Docker named volume for database storage, so that Docker manages the storage lifecycle and I don't need to manage file paths on my host.

#### Acceptance Criteria

1. WHEN a user mounts a Docker named volume to `/data`, THE Container SHALL store the Database_File inside that volume at `/data/nfl_cache.db`
2. THE Container SHALL read from and write to the Database_File at `/data/nfl_cache.db` regardless of whether the `/data` path is backed by a named volume or a bind mount
3. WHEN the named volume already contains a Database_File from a previous container run, THE Container SHALL open the existing database and serve previously cached records without re-fetching from the ESPN API
4. WHEN the named volume is empty on first use, THE Container SHALL create a new Database_File at `/data/nfl_cache.db` and initialize the schema

### Requirement 5: Network and Process Configuration

**User Story:** As a developer, I want the container to handle networking and multiprocessing correctly, so that the application functions properly in a containerized environment.

#### Acceptance Criteria

1. THE Container SHALL bind the HTTP server to `0.0.0.0` (all network interfaces) so that it is reachable from outside the container via Docker port mapping
2. THE Dockerfile SHALL include an EXPOSE directive for the default application port (8080) to document the listening port in image metadata
3. THE Container SHALL allow outbound HTTPS connections to ESPN API endpoints, including DNS resolution of external hostnames, for data fetching
4. THE Container SHALL use the `fork` multiprocessing start method and provide a `/dev/shm` allocation of at least 64 MB so that `ProcessPoolExecutor` can spawn worker processes for parallel Monte Carlo simulation
5. IF Python multiprocessing worker processes fail to start due to resource constraints, THEN THE Container SHALL fall back to single-process execution without crashing

### Requirement 6: Docker Compose Configuration

**User Story:** As a user, I want a default Docker Compose file, so that I can start the containerized application with a single `docker compose up` command without manually specifying mounts and port mappings.

#### Acceptance Criteria

1. THE project SHALL include a `compose.yaml` file in the project root directory
2. THE compose.yaml SHALL define a service that builds the Container_Image using the Dockerfile in the project root as build context
3. THE compose.yaml SHALL declare a named volume in the top-level `volumes` key and mount it to the container path `/data` so that the Database_File at `/data/nfl_cache.db` persists across container restarts
4. THE compose.yaml SHALL map container port 8080 to host port 8080 using Compose variable interpolation (e.g., `${PORT:-8080}:8080`) so that the host port is overridable via shell environment variables
5. THE compose.yaml SHALL pass `PORT` and `SEASON` environment variables to the container using Compose variable interpolation with empty defaults (e.g., `${PORT:-}`, `${SEASON:-}`), allowing users to override them by setting shell environment variables or by defining them in a `.env` file in the project root
6. WHEN a user runs `docker compose up` without setting any environment variables or creating a `.env` file, THE Container SHALL start successfully, bind to port 8080, and respond to HTTP requests within 30 seconds of the command being issued

### Requirement 7: Documentation

**User Story:** As a user, I want clear documentation for running the application in Docker, so that I can get started quickly with either bind mounts or volume mounts.

#### Acceptance Criteria

1. THE project SHALL include a `.dockerignore` file that excludes `.venv/`, `.git/`, `__pycache__/`, `.hypothesis/`, `.pytest_cache/`, `.playwright-mcp/`, and `nfl_cache.db` from the build context
2. THE project README or a dedicated Docker documentation section SHALL provide at least one runnable command example for each of the following scenarios: building the image, running with a bind mount, running with a named volume, configuring environment variables (`PORT`, `SEASON`), and starting via Docker Compose
3. THE documentation SHALL state that Docker is optional and that the existing non-Docker setup (virtual environment with `pip install`) and usage workflow remain fully supported
