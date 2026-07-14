# Stage 1: builder — install the package and its dependencies
FROM python:3.14-slim AS builder

WORKDIR /build

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir --root-user-action=ignore .

# Stage 2: runtime — minimal image with only what's needed to run
FROM python:3.14-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages

# Copy application source
COPY src/ src/

# Copy frontend static assets
COPY frontend/ frontend/

# Copy entrypoint script
COPY docker-entrypoint.py .

# Create data directory for SQLite database (volume mount target)
RUN mkdir -p /data && chmod 777 /data

EXPOSE 8080

ENTRYPOINT ["python", "docker-entrypoint.py"]
