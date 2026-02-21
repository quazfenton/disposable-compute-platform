# Production Dockerfile for Disposable Compute Platform
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt


# Production image
FROM python:3.11-slim

# Labels
LABEL maintainer="Disposable Compute Platform"
LABEL version="2.0.0"

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r dcp && useradd -r -g dcp dcp

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create directories
RUN mkdir -p /app /var/log/dcp /var/lib/dcp/storage \
    && chown -R dcp:dcp /app /var/log/dcp /var/lib/dcp

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=dcp:dcp . .

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    LOG_LEVEL=INFO \
    ENVIRONMENT=production

# Expose ports
EXPOSE 8000
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Switch to non-root user
USER dcp

# Run application
CMD ["uvicorn", "src.api.main_v2:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
