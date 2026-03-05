#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PIDFILE="$PROJECT_DIR/data/.server.pid"

if [ ! -f "$PIDFILE" ]; then
    echo "No PID file found. Server may not be running."
    exit 1
fi

PID="$(cat "$PIDFILE")"

if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping CAME API Sniffer (PID $PID)..."
    kill "$PID"
    # Wait for graceful shutdown (up to 10 seconds)
    for i in $(seq 1 10); do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    # Force kill if still running
    if kill -0 "$PID" 2>/dev/null; then
        echo "Force killing..."
        kill -9 "$PID"
    fi
    echo "Server stopped."
else
    echo "Process $PID is not running."
fi

rm -f "$PIDFILE"
