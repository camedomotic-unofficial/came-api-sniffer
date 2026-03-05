#!/usr/bin/env bash
set -euo pipefail

# Find server PIDs by scanning /proc (works without procps/pgrep)
find_server_pids() {
    for pidnum in $(ls /proc/ 2>/dev/null | grep '^[0-9]*$'); do
        local cmdline
        cmdline=$(tr '\0' ' ' < "/proc/$pidnum/cmdline" 2>/dev/null) || continue
        if echo "$cmdline" | grep -q 'python -m src.main'; then
            echo "$pidnum"
        fi
    done
}

PIDS="$(find_server_pids)"

if [ -z "$PIDS" ]; then
    echo "Server is not running."
    exit 0
fi

echo "Stopping CAME API Sniffer (PID $PIDS)..."
kill $PIDS

# Wait for graceful shutdown (up to 10 seconds)
for i in $(seq 1 10); do
    if [ -z "$(find_server_pids)" ]; then
        echo "Server stopped."
        exit 0
    fi
    sleep 1
done

# Force kill if still running
echo "Force killing..."
kill -9 $PIDS 2>/dev/null || true
echo "Server stopped."
