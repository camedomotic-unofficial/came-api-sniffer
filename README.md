# CAME API Sniffer

A transparent HTTP proxy that sits between the **CAME Domotic Android app** and the **CAME server** on your LAN, intercepting and logging all API traffic. Built for reverse-engineering and understanding the CAME Domotic protocol.

Every request and response is captured, stored in both JSON files and a searchable SQLite database, and displayed in a real-time web dashboard.

```
CAME Android App  --HTTP-->  Proxy (port 80)  --HTTP-->  CAME Server (LAN)
                  <--HTTP--                   <--HTTP--
                                |
                                v
                     JSON files + SQLite DB
                     Web Dashboard (:8081)
```

## Warning

> **This project is highly experimental. Use entirely at your own risk.**
>
> - There are **no guarantees** of correctness, stability, or safety. Things may break.
> - The port redirection scripts (`redirect-port80.sh` / `restore-port80.sh`) modify network settings on your **host machine** using `socat` and `sudo`. **They can interfere with your networking** if something goes wrong. The redirect script also runs `killall socat` which will terminate **any** running socat process on your system.
> - Review every script before running it. Make sure you understand what it does.
> - This tool is intended for **personal use on your own local network** for research and debugging purposes only.
> - Ensure compliance with applicable laws and CAME's terms of service.

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) running on your machine
- [Visual Studio Code](https://code.visualstudio.com/) with the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension
- On macOS: `socat` installed on the host (`brew install socat`) — needed for the port 80 redirect step

### Step 1 — Clone and Open in Dev Container

1. Clone this repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/came-api-sniffer.git
   ```
2. Open the folder in VS Code.
3. VS Code will detect the Dev Container configuration and prompt you to **"Reopen in Container"**. Click it.
   - Or press `Cmd+Shift+P` (macOS) / `Ctrl+Shift+P` (Linux/Windows) and select **Dev Containers: Reopen in Container**.
4. Wait for the container to build. All Python dependencies are installed automatically.

### Step 2 — Configure

Inside the container terminal:

```bash
cp .env.example .env
```

Edit `.env` and set `CAME_HOST` to your CAME server's LAN IP address (e.g. `192.168.1.3`).

### Step 3 — Start the Sniffer

**Option A** — VS Code Task: press `Cmd+Shift+P` → **Tasks: Run Task** → **Start**.

**Option B** — Terminal (inside the container):

```bash
./scripts/start.sh
```

This starts:
- The **proxy** on port 80 (inside the container)
- The **web dashboard** on port 8081 — open [http://localhost:8081](http://localhost:8081) in your browser

### Step 4 — Redirect Port 80 on the Host (macOS)

On macOS, Docker Desktop maps container ports to random host ports. The CAME Android app must connect on **port 80**, so you need to redirect the host's port 80 to the container's mapped port.

1. Check which host port was assigned to the container's port 80. Look in the VS Code **Ports** tab or run `docker ps`.
2. Set `PROXY_PORT` in your `.env` file to that host port number (e.g. `59832`).
3. **On the macOS host terminal** (not inside the container), run:

```bash
sudo ./scripts/redirect-port80.sh
```

This starts a `socat` process that forwards `host:80 → 127.0.0.1:PROXY_PORT`.

> **Caution:** This requires `sudo`, binds to port 80, and kills any existing `socat` processes. Make sure nothing important on your system uses port 80 or socat before running this.

### Step 5 — Point the Android App to the Proxy

In the CAME Domotic Android app, change the server address to **your Mac's LAN IP** (e.g. `192.168.1.100`). The app connects on port 80, hits the proxy, and the proxy forwards everything to the real CAME server. The app won't notice any difference.

### Step 6 — Stop Everything

**Inside the container**, stop the sniffer:

```bash
./scripts/stop.sh
```

Or use the VS Code task: `Cmd+Shift+P` → **Tasks: Run Task** → **Stop**.

**On the macOS host**, remove the port 80 redirect:

```bash
sudo ./scripts/restore-port80.sh
```

> **Important:** Always run the restore script when you're done. Leaving the redirect active keeps `socat` listening on port 80 as root, which will interfere with other services and is a security risk.

## Dashboard

The web dashboard at [http://localhost:8081](http://localhost:8081) shows:

- **Live feed** of captured exchanges (real-time via WebSocket)
- **Full-text search** across request and response bodies
- **Filters** by session ID, app method, and time range
- **Detail view** with headers, parsed JSON body, and response
- **Export** to TXT files (all, by session, or by time range)

## Data Storage

Captured exchanges are stored in `data/`:

| Location | Format | Purpose |
|----------|--------|---------|
| `data/exchanges/*.json` | JSON | One file per exchange, human-readable |
| `data/came_proxy.db` | SQLite | Queryable database with FTS5 full-text search |
| `data/exports/*.txt` | TXT | Exported reports |

## Configuration

All settings are in `.env` (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `CAME_HOST` | *(required)* | CAME server IP on your LAN |
| `CAME_PORT` | `80` | CAME server port |
| `PROXY_PORT` | `80` | Proxy listen port (also used by redirect script) |
| `DASHBOARD_PORT` | `8081` | Dashboard web UI port |
| `DATA_DIR` | `./data` | Storage directory |
| `DB_NAME` | `came_proxy.db` | SQLite database filename |
| `LOG_LEVEL` | `DEBUG` | Logging verbosity |

## License

This project is licensed under the [MIT License](LICENSE).
