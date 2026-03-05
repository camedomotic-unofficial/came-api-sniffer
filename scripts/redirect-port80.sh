#!/usr/bin/env bash
#
# Forwards incoming traffic on port 80 to the proxy port using socat.
# Run on the macOS host (not inside the container). Requires sudo.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"
PIDFILE="/tmp/came-proxy-socat.pid"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi

PROXY_PORT=$(grep -E '^PROXY_PORT=' "$ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')
if [[ -z "$PROXY_PORT" ]]; then
    echo "Error: PROXY_PORT not found in .env"
    exit 1
fi

if [[ "$PROXY_PORT" == "80" ]]; then
    echo "Error: PROXY_PORT is 80, no redirect needed."
    echo "Set PROXY_PORT to the container's forwarded port (e.g. 59832) in .env."
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run with sudo."
    echo "Usage: sudo $0"
    exit 1
fi

if ! command -v socat &>/dev/null; then
    echo "Error: socat not found. Install with: brew install socat"
    exit 1
fi

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Redirect already active (PID $(cat "$PIDFILE"))."
    echo "Run 'sudo ./scripts/restore-port80.sh' to remove it."
    exit 0
fi

# Kill any orphan socat processes from a previous redirect
killall socat 2>/dev/null || true

echo "Forwarding port 80 -> 127.0.0.1:$PROXY_PORT using socat..."
socat TCP-LISTEN:80,fork,reuseaddr TCP:127.0.0.1:"$PROXY_PORT" &
SOCAT_PID=$!
echo $SOCAT_PID > "$PIDFILE"

# Verify socat started successfully
sleep 0.5
if ! kill -0 "$SOCAT_PID" 2>/dev/null; then
    echo "Error: socat failed to start. Port 80 may be unavailable."
    rm -f "$PIDFILE"
    exit 1
fi

echo "Redirect active (PID $(cat "$PIDFILE")): port 80 -> $PROXY_PORT"
echo "Run 'sudo ./scripts/restore-port80.sh' to remove it."
