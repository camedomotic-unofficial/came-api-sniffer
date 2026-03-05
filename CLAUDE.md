# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CAME API Sniffer** is an HTTP reverse proxy with a web dashboard for reverse-engineering and analyzing the CAME Domotic API. It sits between the CAME Domotic Android app and the CAME server, intercepting and logging all HTTP traffic.

**Key Features:**
- Transparent HTTP proxy on port 80
- Dual storage: JSON files (human-readable) + SQLite database (queryable)
- Web dashboard with real-time updates via WebSocket
- Export functionality (TXT format with pretty-printing)
- Full-text search across requests/responses using SQLite FTS5

## Quick Start

### Setup
```bash
cp .env.example .env
# Edit .env to set CAME_HOST to your CAME server's IP
```

### Run
```bash
python src/main.py
```

This starts:
- **Proxy server** on port 80 (receives traffic from CAME app)
- **Dashboard** on port 8081 (http://localhost:8081)

### Development Environment

The project uses **Dev Containers** (VSCode + Docker):
1. Install VSCode with Dev Containers extension
2. Open project in VSCode
3. Press `Cmd+Shift+P` → "Dev Containers: Reopen in Container"
4. VSCode will build and start the container with all dependencies

The devcontainer includes:
- Python 3.14
- VS Code extensions: Claude Code, Python, Pylint, Ruff
- Dependencies installed via `postCreateCommand: pip install -r requirements.txt`

## Architecture

### High-Level Design

```
┌─────────────────┐         ┌──────────────────┐         ┌──────────────┐
│  CAME Domotic   │         │  Proxy Python    │         │ CAME Server  │
│   Android App   │◄──HTTP──┤  (This Project)  │──HTTP──┤  (LAN)       │
│                 │──HTTP──►│                  │◄──HTTP──│              │
└─────────────────┘  :80    └────────┬─────────┘  :80    └──────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
                ┌────────┐      ┌──────────┐    ┌────────┐
                │  JSON  │      │ SQLite   │    │WebSocket│
                │ Files  │      │   DB     │    │ Clients │
                └────────┘      └──────────┘    └────────┘
                    │                ▼
                    └───────►┌────────────────┐
                            │   Dashboard    │
                            │   Web UI       │
                            │   (:8081)      │
                            └────────────────┘
```

### Module Organization

| Module | Purpose |
|--------|---------|
| **main.py** | Entry point; runs proxy + dashboard servers concurrently in one event loop. Handles graceful shutdown on SIGINT/SIGTERM. |
| **proxy.py** | HTTP reverse proxy handler; listens on port 80, forwards requests identically to CAME server (preserving method, path, query string, headers, body), captures responses, extracts metadata |
| **storage.py** | Dual storage manager (JSON + SQLite); handles persistence and queries. Keeps both stores in sync automatically. |
| **dashboard.py** | REST API + WebSocket server; serves web UI and handles client requests. WebSocket broadcasts new exchanges in real-time. |
| **export.py** | Export functionality; generates formatted TXT files with request/response details |
| **config.py** | Configuration loader (reads .env with sensible defaults); logging setup |
| **static/** | Frontend assets (index.html, style.css, app.js). Vanilla JavaScript SPA with no build step. |

### Key Design Patterns

1. **Async/Await**: All I/O is non-blocking (aiohttp, aiosqlite). Single asyncio event loop runs both proxy and dashboard. No blocking operations in the event loop.

2. **Metadata Extraction**: The proxy extracts from JSON request bodies:
   - `session_id` from `sl_client_id` field (can be `null` if body is not JSON or field missing)
   - `app_method` from `sl_appl_msg.cmd_name` → fallback to `sl_cmd` (can be `null`)
   - See "CAME Request Format" section below for context

3. **Transparent Proxy**: Routes all traffic to CAME server **identically**:
   - Same HTTP method, path, query string, body
   - Same headers (only modifying `Host` header to target CAME server)
   - Filters hop-by-hop headers (Connection, Keep-Alive, Transfer-Encoding, etc.)
   - CAME app doesn't perceive any difference

4. **Dual Storage Sync**: Every exchange written to both JSON file and SQLite in parallel (non-blocking). Single `StorageManager` interface hides complexity. Files and DB stay in perfect sync.

5. **Real-Time Updates**: WebSocket pushes summary of new exchanges to all connected dashboard clients. Contains: exchange_id, session_id, app_method, timestamp_start, path, status_code, duration_ms.

## CAME Request Format

CAME API requests follow this JSON structure:

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

**Metadata extraction:**
- `sl_client_id` → **session_id** (groups exchanges, used in filtering and filenames)
- `sl_appl_msg.cmd_name` → **app_method** (shown in dashboard as primary method)
- `sl_cmd` → **app_method fallback** (used if cmd_name not present)

Both can be `null` if the request body is not JSON or fields are missing.

## Data Flow

1. **Incoming Request**: Android app → Proxy (port 80)
2. **Generate Exchange ID**: Create UUID v4 for this exchange
3. **Extraction**: Parse JSON body, extract session_id + app_method
4. **Log Request**: Save request details (JSON + SQLite)
5. **Forward**: Proxy → CAME Server (aiohttp.ClientSession, method/path/query/headers/body identical)
6. **Capture Response**: Receive response, measure duration
7. **Log Response**: Save response details to same exchange record
8. **Storage**: Write to both `data/exchanges/{file}.json` and SQLite (parallel, non-blocking)
9. **Broadcast**: Send new exchange summary via WebSocket to all connected clients
10. **Return**: Response returned identically to app
11. **Query**: Dashboard fetches exchanges via REST API (searches/paginates SQLite, uses FTS5 for text search)

## Configuration

All configuration is in `.env` (defaults in config.py if not set):

```env
CAME_HOST=192.168.x.x          # CAME server IP (required, no default works for all)
CAME_PORT=80                   # CAME server port (default: 80)
PROXY_PORT=80                  # Proxy port (default: 80, must be 80 for CAME app)
DASHBOARD_PORT=8081            # Dashboard port (default: 8081)
DATA_DIR=./data                # Data storage directory
DB_NAME=came_proxy.db           # SQLite database filename
LOG_LEVEL=DEBUG                 # Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
```

## Storage Details

### JSON Files

Location: `data/exchanges/`

**File naming**: `{session_id}_{timestamp}_{exchange_id_short}.json`
- `session_id`: Value of `sl_client_id`, or `no-session` if null
- `timestamp`: Format `YYYYMMDD-HHmmss-fff` (milliseconds), from `timestamp_start`
- `exchange_id_short`: First 8 characters of UUID v4

Example: `5046b5a9_20250315-143022-456_a1b2c3d4.json`

**Format**: See README.md for JSON structure. Both request and response bodies are stored:
- If body is valid JSON: stored as object
- If body is not JSON: stored as string
- Either can have syntax highlighting in dashboard

### SQLite Database

Location: `data/came_proxy.db`

**Single `exchanges` table** with columns:
- `exchange_id` (TEXT PRIMARY KEY) — UUID v4
- `session_id`, `app_method`, `method` (HTTP), `path`, `query_string`
- `timestamp_start`, `timestamp_end`, `duration_ms`
- `request_headers`, `request_body`, `response_headers`, `response_body` (all stored as JSON strings)
- `status_code`, `error` (error message if request failed)

**Indexes**:
- `idx_timestamp` — find by timestamp
- `idx_session_id` — find by session
- `idx_app_method` — find by method
- `idx_path` — find by path

**FTS5** (Full-Text Search): Virtual table `exchanges_fts` indexes `exchange_id`, `session_id`, `app_method`, `path`, `request_body`, `response_body` with automatic sync triggers.

**Database features**:
- WAL mode enabled (better concurrency)
- `created_at` field with default current timestamp

## REST API Endpoints

All endpoints at `http://localhost:8081`:

**Exchanges:**
- `GET /api/exchanges` — List with pagination & filters (page, page_size, search, session_id, app_method, from_ts, to_ts)
- `GET /api/exchanges/{exchange_id}` — Full details of single exchange

**Metadata:**
- `GET /api/sessions` — Distinct sessions with exchange counts
- `GET /api/methods` — Distinct methods with counts
- `GET /api/stats` — Aggregate stats (total exchanges, top paths, etc.)

**Mutations:**
- `DELETE /api/exchanges` — Clear all data (⚠️ irreversible)
- `GET /api/export` — Export to TXT (mode: all/session/range, with session_id/from_ts/to_ts params)

**WebSocket:**
- `GET /ws` — Real-time stream of new exchanges

## Common Development Tasks

### Adding a New API Endpoint

1. Add handler method in `DashboardBackend` class (dashboard.py)
2. Register route in `create_dashboard_app()` function
3. Query data using `storage = await get_storage()` and call its methods

Example:
```python
async def api_new_endpoint(self, request: web.Request) -> web.Response:
    storage = await get_storage()
    # ... query data ...
    return web.json_response({...})
```

### Broadcasting to WebSocket Clients

From `proxy.py` after saving an exchange:

```python
# Get dashboard reference from proxy app
dashboard = request.app.get("dashboard")
if dashboard:
    await dashboard.broadcast_new_exchange(exchange_data)
```

### Modifying Export Format

Edit the `export_to_txt()` function in export.py. The export writes to `data/exports/{filename}.txt` and is called by the `/api/export` endpoint.

### Adding Frontend Features

Modify files in `src/static/`:
- `index.html` — HTML structure and layout
- `style.css` — Dark theme styling
- `app.js` — JavaScript logic, WebSocket connection, API calls

Frontend uses vanilla JavaScript (no build step). Changes are immediately visible when dashboard is reloaded.

### Understanding Request/Response Capture

Proxy.py's `handle_request()` method:
1. Reads entire request body into memory
2. Parses as JSON and extracts metadata
3. Creates aiohttp request to CAME server
4. Waits for response (with timeout)
5. Reads entire response body
6. Stores complete exchange to storage

This approach ensures zero data loss but uses more memory for large payloads. If scaling to very high traffic, consider streaming.

## Troubleshooting Notes

- **Port 80 in use**: Use `lsof -i :80` to find what's using it
- **CAME server unreachable**: Check `CAME_HOST` and `CAME_PORT` in .env, verify network connectivity
- **No exchanges captured**: Verify Android app is configured to proxy through your Mac's IP
- **WebSocket not connecting**: Check browser console (F12), verify proxy is running
- **Database locked errors**: SQLite using WAL (Write-Ahead Logging) mode for better concurrency; check for stale processes

## Important Implementation Details

### Request Processing
- **Routing**: Preserves all request path segments and query strings (e.g., `/api/v1/endpoint?foo=bar`)
- **Headers**: Forwards identically (only modifying `Host` to target CAME server)
- **Headers filtering**: Removes hop-by-hop headers before forwarding:
  - Connection, Keep-Alive, Transfer-Encoding, Content-Length (recalculated if needed)
  - Proxy-related headers
- **Body handling**: Forwards request body identically, whether JSON or binary

### Error Handling
- **502 Bad Gateway**: Returned if CAME server is unreachable (stored in exchange `error` field)
- **504 Gateway Timeout**: Returned if CAME server doesn't respond within timeout (30s total, 10s connect)
- **Non-fatal errors**: Logged to console and DB; proxy continues running (doesn't crash)
- **Malformed requests**: If body is not JSON, `session_id` and `app_method` are `null` (processing continues normally)

### Database & Storage
- **Dual write**: Every exchange written to both JSON file and SQLite in parallel (non-blocking)
- **WAL mode**: SQLite uses Write-Ahead Logging for better concurrency
- **JSON encoding**: Handles various encodings (UTF-8 default); falls back gracefully
- **Content-Length**: Recalculated after header modifications if needed

### Performance & Scaling
- **Event loop**: Single asyncio loop handles ~5 req/min comfortably (design allows scaling to higher volumes)
- **Memory**: Loads entire request/response bodies into memory (suitable for typical API traffic; would need streaming for very large payloads)
- **Graceful shutdown**: On SIGINT/SIGTERM, completes in-flight exchanges, closes DB, exits cleanly

## DevContainer & Docker Notes

**VSCode Dev Containers** (`.devcontainer/devcontainer.json`):
- Base image: `python:3.14-slim`
- Working directory: `/workspace` (maps to project root)
- **Port forwarding**: 80 (proxy), 8081 (dashboard)
- **Run args**: `--network=host` (critical for LAN connectivity)
- **Post-create command**: `pip install -r requirements.txt`
- **Extensions**: Python, Pylint, Ruff, Claude Code

**Important**: The `--network=host` flag is **necessary** for the Android app to reach the proxy on the LAN. Without it, the proxy would be isolated in Docker's network and unreachable from the LAN. On macOS Docker Desktop with limitations on `--network=host`, ensure ports 80 and 8081 are properly forwarded.

**Port 80 permissions**:
- On **macOS/Docker Desktop**: May need to close other services on port 80 (use `lsof -i :80`)
- On **Linux**: May need `CAP_NET_BIND_SERVICE` capability or run with elevated privileges
- On **Windows**: Run with appropriate permissions

## File Paths to Know

- `data/exchanges/` — Individual JSON exchange files (one per HTTP request/response)
- `data/exports/` — Exported TXT files (generated by dashboard)
- `data/came_proxy.db` — SQLite database with all exchanges
- `src/static/` — Frontend assets (HTML, CSS, JS) served from aiohttp

## Debugging & Analysis

### Direct Database Queries

For advanced analysis, query the SQLite database directly:

```bash
# Open SQLite CLI
sqlite3 data/came_proxy.db

# Example queries
SELECT COUNT(*) FROM exchanges;
SELECT DISTINCT session_id FROM exchanges;
SELECT * FROM exchanges WHERE session_id = '5046b5a9';
SELECT * FROM exchanges WHERE app_method = 'feature_list_req';
SELECT path, COUNT(*) FROM exchanges GROUP BY path ORDER BY COUNT(*) DESC;
```

### Full-Text Search

Search request/response bodies using FTS5:

```sql
SELECT exchange_id, session_id, app_method FROM exchanges
WHERE exchange_id IN (
  SELECT exchange_id FROM exchanges_fts WHERE exchanges_fts MATCH 'search_term'
);
```

### Export & Analysis

From the dashboard or CLI:
- `GET /api/export?mode=all` — download all exchanges as TXT
- `GET /api/export?mode=session&session_id=XXX` — download session as TXT
- `GET /api/export?mode=range&from_ts=2025-03-15T00:00:00Z&to_ts=2025-03-15T23:59:59Z` — download time range as TXT
