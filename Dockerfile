# Stage 1: Builder
FROM python:3.12-slim-bookworm AS builder

# Install system build dependencies (required for llama-cpp-python compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Setup working directory
WORKDIR /app

# Copy dependency files AND Readme (Required for hatchling build)
COPY pyproject.toml uv.lock README.md ./

# Install dependencies into a virtual environment
# We compile llama-cpp-python for CPU here
ENV CMAKE_ARGS="-DGGML_NATIVE=OFF"
RUN uv sync --frozen --no-dev

# Stage 2: Runner
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install minimal runtime deps (libgomp for openmp support in llama.cpp)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
# Fix: PYTHONPATH is redundant if we install the package, but harmless.
# Removing the undefined variable warning by setting it explicitly or removing it.
ENV PYTHONPATH="/app/src"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AUTO_DOWNLOAD_MODELS=true

# Copy Source Code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Copy Default Configs (Users can override these via volumes)
COPY config/ ./config/

# Create directories for data and models
RUN mkdir -p /app/models /app/data

# Expose API Port
EXPOSE 8000

# Set Entrypoint
COPY scripts/entrypoint.sh /app/scripts/entrypoint.sh
RUN chmod +x /app/scripts/entrypoint.sh

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
