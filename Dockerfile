# ── Stage 1: build ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="TorrentBot"

# Install system dependencies: aria2 + ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    aria2 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Verify tools
RUN aria2c --version && ffmpeg -version && python --version

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Create downloads directory
RUN mkdir -p /downloads

# Non-root user for security
RUN useradd -r -s /bin/false botuser && chown -R botuser:botuser /app /downloads

USER botuser

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "bot.py"]
