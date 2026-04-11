#!/bin/bash
set -e

LITESTREAM_CONFIG="/app/litestream.yml"

# Restore the SQLite database from GCS (if a backup exists)
echo "🔄 Litestream: Restoring database from GCS..."
litestream restore -config "$LITESTREAM_CONFIG" -if-db-not-exists -if-replica-exists /app/cache/financebro.db

echo "✅ Litestream: Starting replication + app..."

# Start Litestream replication in the background, then start the app
exec litestream replicate -config "$LITESTREAM_CONFIG" -exec "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"
