# ----------- Build Stage -----------
FROM ghcr.io/astral-sh/uv:python3.12-alpine AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (without the project itself)
RUN uv sync --frozen --no-install-project --no-dev

# Copy project files
COPY . /app

# Install the project
RUN uv sync --frozen --no-dev

# ----------- Runtime Stage -----------
FROM python:3.12-alpine AS runtime

# Create non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy entrypoint
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "-u", "telefwd/main.py"]
