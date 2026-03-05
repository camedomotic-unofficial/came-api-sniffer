#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PIDFILE="$PROJECT_DIR/data/.server.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Server is already running (PID $(cat "$PIDFILE"))"
    exit 1
fi

mkdir -p "$PROJECT_DIR/data"

echo "Starting CAME API Sniffer..."
cd "$PROJECT_DIR"
python src/main.py &
SERVER_PID=$!
echo "$SERVER_PID" > "$PIDFILE"
echo "Server started (PID $SERVER_PID)"
echo "  Proxy:     http://localhost:80"
echo "  Dashboard: http://localhost:8081"
