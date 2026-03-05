#!/usr/bin/env bash
#
# Stops the socat port 80 forwarder started by redirect-port80.sh.
# Run on the macOS host (not inside the container). Requires sudo.
#
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run with sudo."
    echo "Usage: sudo $0"
    exit 1
fi

PIDFILE="/tmp/came-proxy-socat.pid"

if [[ ! -f "$PIDFILE" ]]; then
    echo "No redirect active (pidfile not found)."
    exit 0
fi

PID=$(cat "$PIDFILE")

echo "Stopping port 80 forwarder..."
# Kill all socat processes (parent + any forked children)
killall socat 2>/dev/null || true
rm -f "$PIDFILE"

echo "Redirect removed."
