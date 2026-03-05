#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

mkdir -p "$PROJECT_DIR/data"

echo "Starting CAME API Sniffer..."
echo "  Proxy:     http://localhost:80"
echo "  Dashboard: http://localhost:8081"
echo ""

cd "$PROJECT_DIR"
exec python -m src.main
