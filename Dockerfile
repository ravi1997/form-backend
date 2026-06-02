# Multi-stage-ready slim base — ~750MB smaller than full bookworm image.
# libmagic1 is available in slim images (no build-essential needed).
FROM python:3.10-slim-bookworm

# Reproducible builds: write no .pyc files; flush stdout/stderr immediately.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# System dependencies — only what the runtime needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies before copying source (layer-cache friendly).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source.
COPY . /app/

# Ensure logs directory exists.
RUN mkdir -p /app/logs

# Run as a non-root user (security best practice).
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 6000

# Default command: Runs the production server
CMD ["gunicorn", "--bind", "0.0.0.0:6000", "--workers", "3", "--threads", "4", "--timeout", "120", "--graceful-timeout", "30", "app:create_app()"]
