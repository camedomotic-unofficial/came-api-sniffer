# CAME API Sniffer

A comprehensive reverse HTTP proxy with logging and analysis dashboard for reverse-engineering the CAME Domotic API. Intercepts and analyzes all traffic between the CAME Domotic Android app and the CAME server on the LAN.

## Architecture

```
┌──────────────┐         ┌──────────────────┐         ┌──────────────┐
│ App Android   │──HTTP──▶│   Proxy Python   │──HTTP──▶│ Server CAME  │
│ CAME Domotic │◀──HTTP──│  (devcontainer)  │◀──HTTP──│ (LAN, :80)   │
│ (IP → proxy) │  :80    │      :80         │  :80    │              │
└──────────────┘         └──────────────────┘         └──────────────┘
                              │         │
                              ▼         ▼
                         ┌────────┐ ┌────────┐
                         │ SQLite │ │  JSON  │
                         │   DB   │ │ files  │
                         └────────┘ └────────┘
                              │
                              ▼
                         ┌────────────┐
                         │ Dashboard  │
                         │  Web UI    │
                         │   :8081    │
                         └────────────┘
```

## Prerequisites

- Docker and Docker Desktop (or Podman)
- VSCode with Dev Containers extension
- macOS, Linux, or Windows with WSL2
- Python 3.14 (inside container)

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/yourusername/came-api-sniffer.git
cd came-api-sniffer
cp .env.example .env
```

### 2. Configure CAME Server

Edit `.env` and set `CAME_HOST` to your CAME server's IP address:

```env
CAME_HOST=192.168.x.x
CAME_PORT=80
```

### 3. Open in VSCode Container

1. Open the project in VSCode
2. Press `Cmd+Shift+P` (or `Ctrl+Shift+P` on Linux/Windows)
3. Select "Dev Containers: Reopen in Container"
4. VSCode will build and start the container

### 4. Start the Proxy

```bash
python src/main.py
```

The proxy starts on ports:
- **80** (proxy server) — receives requests from Android app
- **8081** (dashboard) — open in browser: `http://localhost:8081`

### 5. Configure Android App

1. Open CAME Domotic app
2. Go to Settings
3. Find the server IP setting
4. Change it to your Mac's IP on the LAN (e.g., `192.168.1.100`)
5. The app will now communicate through the proxy

**Important:** You do NOT need to configure HTTP proxy in Android settings. Only change the server IP in the CAME app itself.

## Dashboard Usage

### View Exchanges

- **List view** shows all captured HTTP exchanges in real-time
- **Columns**: Timestamp, Session ID, App Method, Path, HTTP Status, Duration
- **Real-time updates**: New exchanges appear automatically (if auto-refresh is enabled)
- **Auto-refresh toggle**: Enable/disable automatic list updates

### Search & Filter

- **Full-text search**: Search in request/response bodies, paths
- **Session ID**: Filter by specific session (autocomplete)
- **App Method**: Filter by cmd_name or sl_cmd
- **Date range**: Filter by timestamp range (From/To)

### View Exchange Details

- Click any row to open the detail panel (right side)
- Shows complete request and response with headers and body
- Headers are collapsible (click to expand/collapse)
- JSON bodies are pretty-printed with syntax highlighting

### Actions

- **Copy as cURL**: Generate exact curl command for the request
- **Export as TXT**: Download this exchange as formatted text file

### Export Data

Click the **Export ↓** button to export in multiple modes:

- **Export Results**: Current filtered/searched results
- **Export Session**: All exchanges for a specific session
- **Export Range**: All exchanges in a date/time range
- **Export All**: All captured exchanges

Exports are saved as `.txt` files with pretty-printed formatting, readable in any text editor.

## Data Storage

### Directory Structure

```
data/
├── exchanges/           # Individual JSON files (request + response)
├── exports/            # Exported TXT files
└── came_proxy.db       # SQLite database
```

### JSON Files

Each exchange is saved as:
```
{session_id}_{timestamp}_{exchange_id_short}.json
```

Example:
```
5046b5a9_20250315-143022-456_a1b2c3d4.json
```

Format:
```json
{
  "exchange_id": "a1b2c3d4-...-uuid",
  "session_id": "5046b5a9",
  "app_method": "feature_list_req",
  "timestamp_start": "2025-03-15T14:30:22.456Z",
  "timestamp_end": "2025-03-15T14:30:22.789Z",
  "duration_ms": 333,
  "request": {
    "method": "POST",
    "path": "/endpoint",
    "query_string": "",
    "headers": { "Content-Type": "application/json", ... },
    "body": { ... }
  },
  "response": {
    "status_code": 200,
    "headers": { ... },
    "body": { ... }
  },
  "error": null
}
```

### SQLite Database

The database contains a single `exchanges` table with indexes for fast querying:
- `idx_timestamp` — find exchanges by time
- `idx_session_id` — find exchanges by session
- `idx_app_method` — find exchanges by method
- `idx_path` — find exchanges by path

Full-text search (FTS5) enabled for rapid searching across bodies and paths.

## API Endpoints

All endpoints are available at `http://localhost:8081`

### REST API

#### `GET /api/exchanges`

List exchanges with pagination and filters.

Query parameters:
- `page`: Page number (default: 1)
- `page_size`: Results per page (default: 20)
- `search`: Full-text search query
- `session_id`: Filter by session ID
- `app_method`: Filter by app method
- `from_ts`: Start timestamp (ISO 8601)
- `to_ts`: End timestamp (ISO 8601)

Response:
```json
{
  "exchanges": [...],
  "page": 1,
  "page_size": 20,
  "total_count": 150,
  "total_pages": 8
}
```

#### `GET /api/exchanges/{exchange_id}`

Get full details of single exchange.

#### `GET /api/sessions`

List distinct sessions with exchange counts.

#### `GET /api/methods`

List distinct app methods with counts.

#### `GET /api/stats`

Aggregate statistics:
```json
{
  "total_exchanges": 150,
  "distinct_sessions": 3,
  "distinct_methods": 25,
  "top_paths": [...]
}
```

#### `DELETE /api/exchanges`

Delete all exchanges (⚠️ irreversible).

#### `GET /api/export`

Export exchanges to TXT file.

Parameters:
- `mode`: `all`, `session`, or `range`
- `session_id`: Required for mode=session
- `from_ts`, `to_ts`: Required for mode=range

### WebSocket

#### `GET /ws`

Real-time stream of new exchanges. Server sends JSON messages:
```json
{
  "type": "new_exchange",
  "exchange_id": "...",
  "session_id": "...",
  "app_method": "...",
  "timestamp_start": "...",
  "path": "...",
  "duration_ms": 123,
  "status_code": 200
}
```

## Configuration

### .env File

```env
# Server CAME target (required)
CAME_HOST=192.168.x.x
CAME_PORT=80

# Proxy (must be 80 for Android app compatibility)
PROXY_PORT=80

# Dashboard web UI
DASHBOARD_PORT=8081

# Storage
DATA_DIR=./data
DB_NAME=came_proxy.db

# Logging
LOG_LEVEL=DEBUG
```

All variables have sensible defaults. Only required configuration is `CAME_HOST`.

## Request/Response Format

The CAME API uses JSON with a specific structure. The proxy extracts:

- **Session ID**: `sl_client_id` field → stored as `session_id`
- **App Method**: `sl_appl_msg.cmd_name` or fallback `sl_cmd` → stored as `app_method`

Example request:
```json
{
  "sl_appl_msg": {
    "client": "5046b5a9",
    "cmd_name": "feature_list_req",
    "cseq": 1
  },
  "sl_appl_msg_type": "domo",
  "sl_client_id": "5046b5a9",
  "sl_cmd": "sl_data_req"
}
```

The proxy is completely transparent — the CAME app cannot tell it's communicating through a proxy.

## Troubleshooting

### Port 80 Not Available

**macOS/Docker Desktop:**
- Close other services using port 80
- Use `lsof -i :80` to find what's using port 80
- Kill the process or use a different port (change `PROXY_PORT`)

**Linux:**
- May need `CAP_NET_BIND_SERVICE`: run container with elevated privileges
- Or use a port >1024 (e.g., `PROXY_PORT=8080`)

**Note:** Android app requires port 80 or 8080 to communicate. Some firewalls may block it.

### App Can't Connect to Proxy

1. Verify the Mac's LAN IP: `ifconfig | grep "inet "`
2. Verify Android device is on same network (ping the Mac's IP from Android)
3. Check firewall allows incoming connections on port 80/8081
4. Verify Android app has the correct server IP configured

### WebSocket Not Connecting

- Check browser console (F12) for WebSocket errors
- Verify `http://localhost:8081/ws` is accessible
- Some corporate firewalls block WebSockets

### No Exchanges Captured

1. Verify proxy is running (`python src/main.py`)
2. Check proxy logs for errors
3. Verify CAME_HOST and CAME_PORT are correct
4. Try accessing CAME server directly: `curl http://{CAME_HOST}:{CAME_PORT}/`

## Development

### Project Structure

```
came-api-sniffer/
├── .devcontainer/
│   ├── devcontainer.json
│   └── Dockerfile
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── config.py            # Configuration
│   ├── proxy.py             # HTTP reverse proxy
│   ├── storage.py           # Dual storage (JSON + SQLite)
│   ├── export.py            # Export functionality
│   ├── dashboard.py         # Dashboard REST API + WebSocket
│   └── static/
│       ├── index.html       # Dashboard UI
│       ├── style.css        # Dark theme
│       └── app.js           # Frontend JavaScript
├── data/                    # Created at runtime
├── .env                     # Configuration (gitignored)
├── .env.example
├── requirements.txt
├── README.md
└── .gitignore
```

### Code Style

- Python: PEP 8, type hints throughout
- Async/await for all I/O operations
- Logging instead of print statements
- Comprehensive error handling

### Adding New Features

All components follow the pattern:
1. **storage.py** — Persist data
2. **proxy.py** or **dashboard.py** — Business logic
3. **index.html** + **app.js** — UI

Keep the proxy transparent and non-blocking. Use async/await for all I/O.

## Technical Details

### Dual Storage System

- **JSON files**: Human-readable, self-contained, easy to share
- **SQLite database**: Fast querying, indexing, FTS5 full-text search
- Both stay in sync; single StorageManager interface

### Async Architecture

- Single asyncio event loop runs proxy + dashboard concurrently
- All I/O (HTTP, database, file) non-blocking
- Handles ~5 req/min comfortably; scales to higher volumes

### Real-Time Updates

- WebSocket connection pushes new exchanges to all connected clients
- Dashboard auto-refreshes via WebSocket (or manual refresh if disabled)
- Badge shows pending exchanges when auto-refresh is off

### Export Format

Exports are TXT files with pretty-printed formatting:
```
══════════════════════════════════════════════════════════════════
EXCHANGE: a1b2c3d4-1234-5678-9012-abcdef123456
SESSION:  5046b5a9
METHOD:   feature_list_req
TIME:     2025-03-15T14:30:22.456Z → 2025-03-15T14:30:22.789Z (333ms)
══════════════════════════════════════════════════════════════════

────────────────────────────────────────────────────────────────────
REQUEST
────────────────────────────────────────────────────────────────────
POST /endpoint

Headers:
  Content-Type: application/json

Body:
{
  "sl_appl_msg": { ... },
  ...
}

────────────────────────────────────────────────────────────────────
RESPONSE
────────────────────────────────────────────────────────────────────
Status: 200

Headers:
  Content-Type: application/json

Body:
{
  ...
}

══════════════════════════════════════════════════════════════════
```

## License

This project is provided as-is for reverse engineering and educational purposes.

## Support

For issues, questions, or suggestions:
1. Check this README
2. Review logs: Proxy and dashboard output to console
3. Check browser console (F12) for frontend errors
4. Examine data in `data/exchanges/` directory

## Disclaimer

This tool is designed for analyzing your own CAME server and Android app in a controlled environment. Ensure compliance with applicable laws and CAME's terms of service before using.
