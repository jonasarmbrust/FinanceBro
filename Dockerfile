# FinanceBro - Production Container with Litestream
FROM python:3.12-slim

# System deps + Litestream
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc wget \
    && rm -rf /var/lib/apt/lists/*

# Install Litestream (SQLite → GCS replication)
RUN wget -qO- https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.tar.gz \
    | tar xz -C /usr/local/bin/

# Non-root user
RUN useradd -m -r appuser

WORKDIR /app

# Install Python deps (without Playwright)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y playwright 2>/dev/null || true

# Copy application
COPY . .

# Fix Windows line endings in shell script + set permissions
RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

# Create cache directory + set permissions
RUN mkdir -p /app/cache && chown -R appuser:appuser /app

USER appuser

# Cloud Run sets $PORT automatically
ENV PORT=8080
ENV ENVIRONMENT=production

EXPOSE ${PORT}

# Use Litestream wrapper: restore → replicate → uvicorn
CMD ["/app/start.sh"]
