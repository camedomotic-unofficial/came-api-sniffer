# CAME Domotic HTTP Proxy — Specifiche Tecniche

## Obiettivo

Realizzare un **reverse proxy HTTP con logging** per intercettare, registrare e analizzare il traffico REST/JSON tra l'app mobile CAME Domotic (Android) e il server domotico CAME sulla rete LAN domestica.

Lo scopo è fare reverse engineering dell'API proprietaria CAME Domotic osservando request e response in modo trasparente.

---

## Architettura

```
┌──────────────┐         ┌──────────────────┐         ┌──────────────┐
│  App Android  │──HTTP──▶│   Proxy Python   │──HTTP──▶│ Server CAME  │
│  CAME Domotic │◀──HTTP──│  (devcontainer)  │◀──HTTP──│  (LAN, :80)  │
│  (IP → proxy) │  :80    │      :80         │  :80    │              │
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

### Approccio di intercettazione

L'app Android CAME non permette di configurare la porta del server, solo l'IP. Pertanto:

1. **Il proxy ascolta sulla porta 80**, identica a quella del server CAME reale.
2. Nell'app Android si imposta l'IP del Mac (dove gira il devcontainer) come indirizzo del server.
3. L'app comunica col proxy credendo che sia il server CAME.
4. Il proxy inoltra tutto al server CAME reale (il cui IP è configurato nel `.env`).

**Non si usa il proxy HTTP di Android** (che redirige tutto il traffico del telefono). Si cambia solo l'IP del server nell'app CAME.

### Flusso operativo

1. L'app Android invia una request HTTP sulla porta 80 all'IP del proxy.
2. Il proxy riceve la request.
3. Il proxy estrae il `session_id` dal body JSON (campo `sl_client_id`), se disponibile.
4. Il proxy estrae il metodo applicativo dal body JSON (campo `sl_appl_msg.cmd_name`, con fallback su `sl_cmd`), se disponibile.
5. Il proxy logga la request (JSON file + SQLite).
6. Il proxy inoltra la request **identica** (metodo HTTP, headers, body, query string) al server CAME reale.
7. Il proxy riceve la response dal server CAME.
8. Il proxy logga la response (JSON file + SQLite), associandola alla request tramite `exchange_id`.
9. Il proxy notifica la dashboard via WebSocket.
10. Il proxy restituisce la response **identica** all'app.

Il proxy deve essere **completamente trasparente**: l'app non deve percepire alcuna differenza rispetto a comunicare direttamente col server.

---

## Formato delle request CAME

Le request dell'app CAME hanno generalmente questa struttura JSON:

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

Campi rilevanti per il proxy:

| Campo | Significato | Uso nel proxy |
|---|---|---|
| `sl_client_id` | ID di sessione client | **Session ID** — usato per raggruppare gli exchange, per il nome dei file JSON, per filtri e per l'export |
| `sl_appl_msg.cmd_name` | Comando applicativo specifico | **Metodo applicativo primario** — mostrato nella dashboard come "metodo" |
| `sl_cmd` | Comando di livello trasporto | **Metodo applicativo di fallback** — usato se `cmd_name` non è presente |

---

## Stack tecnologico

| Componente | Tecnologia |
|---|---|
| Linguaggio | **Python 3.14** |
| Framework proxy | **aiohttp ≥ 3.11** (server + client) |
| Database | **SQLite** (via **aiosqlite ≥ 0.21**) |
| Dashboard web | **aiohttp** (stesso processo, porta separata) + **HTML/JS vanilla** |
| Real-time updates | **WebSocket** (aiohttp WebSocket server → dashboard) |
| Configurazione | File **`.env`** (via **python-dotenv ≥ 1.1**) |
| Containerizzazione | **VSCode devcontainer** (Docker) |
| Version control | **Git** → push su **GitHub** |

---

## Componenti

### 1. Proxy Core (`proxy.py`)

Reverse proxy aiohttp che ascolta sulla **porta 80** e gestisce qualsiasi metodo HTTP.

**Comportamento per ogni request ricevuta:**

1. Genera un `exchange_id` univoco (UUID v4).
2. Cattura timestamp, metodo HTTP, URL path + query string, headers, body.
3. Parsa il body JSON (se valido) ed estrae:
   - `session_id` ← campo `sl_client_id` (può essere `null` se il body non è JSON o il campo non esiste).
   - `app_method` ← campo `sl_appl_msg.cmd_name`, con fallback su `sl_cmd` (può essere `null`).
4. Salva la request (JSON file + SQLite).
5. Costruisce la request verso il server CAME target:
   - Stessa path e query string.
   - Stesso metodo HTTP.
   - Stessi headers (rimuovendo/adattando solo `Host` per puntare al CAME target).
   - Stesso body.
6. Invia la request al server CAME e attende la response.
7. Cattura la response: status code, headers, body, tempo di risposta (ms).
8. Salva la response (JSON + SQLite), associata allo stesso `exchange_id`.
9. Notifica la dashboard via WebSocket (nuovo exchange completato).
10. Restituisce la response all'app, identica (status, headers, body).

**Gestione errori:**
- Se il server CAME non è raggiungibile → restituire `502 Bad Gateway` all'app e loggare l'errore.
- Se il server CAME risponde con timeout → restituire `504 Gateway Timeout` all'app e loggare.
- Ogni errore deve essere loggato sia su console che nel DB.

### 2. Storage Layer (`storage.py`)

Modulo che espone un'interfaccia unificata per il salvataggio duale (JSON + SQLite).

#### 2a. JSON File Storage

- Directory: `./data/exchanges/`
- Un file JSON per ogni exchange (request + response insieme).
- **Nome file**: `{session_id}_{timestamp}_{exchange_id}.json`
  - `session_id`: valore di `sl_client_id`, oppure `no-session` se non disponibile.
  - `timestamp`: formato `YYYYMMDD-HHmmss-fff` (millisecondi).
  - `exchange_id`: UUID v4 abbreviato (primi 8 caratteri).
  - Esempio: `5046b5a9_20250315-143022-456_a1b2c3d4.json`
- Formato:

```json
{
  "exchange_id": "a1b2c3d4-...-full-uuid",
  "session_id": "5046b5a9",
  "app_method": "feature_list_req",
  "timestamp_start": "2025-03-15T14:30:22.456Z",
  "timestamp_end": "2025-03-15T14:30:22.789Z",
  "duration_ms": 333,
  "request": {
    "method": "POST",
    "path": "/endpoint",
    "query_string": "",
    "headers": { "Content-Type": "application/json", "...": "..." },
    "body": {
      "sl_appl_msg": { "client": "5046b5a9", "cmd_name": "feature_list_req", "cseq": 1 },
      "sl_appl_msg_type": "domo",
      "sl_client_id": "5046b5a9",
      "sl_cmd": "sl_data_req"
    }
  },
  "response": {
    "status_code": 200,
    "headers": { "Content-Type": "application/json", "...": "..." },
    "body": { "...": "..." }
  },
  "error": null
}
```

- Se il body è JSON valido, salvarlo come oggetto JSON (non come stringa escaped).
- Se il body non è JSON, salvarlo come stringa.

#### 2b. SQLite Database

- File: `./data/came_proxy.db`
- Una singola tabella `exchanges`:

```sql
CREATE TABLE exchanges (
    exchange_id      TEXT PRIMARY KEY,
    session_id       TEXT,                -- sl_client_id dalla request
    app_method       TEXT,                -- cmd_name o fallback sl_cmd
    timestamp_start  TEXT NOT NULL,       -- ISO 8601
    timestamp_end    TEXT,                -- ISO 8601
    duration_ms      INTEGER,
    method           TEXT NOT NULL,       -- metodo HTTP (GET, POST, ecc.)
    path             TEXT NOT NULL,
    query_string     TEXT DEFAULT '',
    request_headers  TEXT NOT NULL,       -- JSON string
    request_body     TEXT,                -- JSON string o raw text
    status_code      INTEGER,
    response_headers TEXT,                -- JSON string
    response_body    TEXT,                -- JSON string o raw text
    error            TEXT,                -- messaggio di errore se presente
    created_at       TEXT DEFAULT (datetime('now'))
);

-- Indici
CREATE INDEX idx_timestamp ON exchanges(timestamp_start);
CREATE INDEX idx_session_id ON exchanges(session_id);
CREATE INDEX idx_app_method ON exchanges(app_method);
CREATE INDEX idx_path ON exchanges(path);
```

**Full-text search:** indice FTS5 per ricerche testuali rapide:

```sql
CREATE VIRTUAL TABLE exchanges_fts USING fts5(
    exchange_id,
    session_id,
    app_method,
    path,
    request_body,
    response_body,
    content='exchanges',
    content_rowid='rowid'
);
```

Con i relativi trigger per tenere sincronizzato l'indice FTS con la tabella principale.

### 3. Export (`export.py`)

Modulo per esportare gli exchange in vari formati e con vari filtri.

**Modalità di export:**

1. **Per session ID** — tutti gli exchange con un determinato `session_id`.
2. **Per intervallo data/ora** — tutti gli exchange con `timestamp_start` compreso in un range `[from, to]`.
3. **Tutti** — export completo di tutti gli exchange nel DB.

**Formato di export:**

- Un **singolo file TXT** contenente tutti gli exchange filtrati, formattati leggibilmente. Ogni exchange usa lo stesso formato del "Esporta come TXT" del pannello dettaglio (con separatori `════...`, sezioni REQUEST e RESPONSE, headers e body pretty-printed). Gli exchange sono concatenati uno dopo l'altro, separati dal doppio separatore.
- Il nome del file TXT indica il filtro applicato:
  - `export_session_{session_id}_{timestamp}.txt`
  - `export_range_{from}_{to}_{timestamp}.txt`
  - `export_all_{timestamp}.txt`
- Directory di output: `./data/exports/`

### 4. Dashboard Web (`dashboard.py` + `static/`)

Una web UI servita su una porta separata per visualizzare e analizzare il traffico.

#### 4a. Backend Dashboard

- Servita da aiohttp sullo stesso processo del proxy, ma su **porta 8081** (configurabile).
- **Endpoint REST:**
  - `GET /api/exchanges` — lista paginata degli exchange, ordinati per timestamp decrescente (più recenti in cima). Parametri:
    - `page`, `page_size` — paginazione.
    - `search` — ricerca full-text (su path, request_body, response_body).
    - `session_id` — filtro per session ID esatto.
    - `app_method` — filtro per metodo applicativo (cmd_name / sl_cmd).
    - `from_ts`, `to_ts` — filtro per intervallo data/ora (ISO 8601).
  - `GET /api/exchanges/{exchange_id}` — dettaglio singolo exchange.
  - `GET /api/sessions` — lista dei session ID distinti con conteggio exchange per ciascuno.
  - `GET /api/methods` — lista dei metodi applicativi distinti con conteggio exchange per ciascuno.
  - `GET /api/stats` — statistiche base (totale exchange, breakdown per session, per metodo applicativo, per path).
  - `DELETE /api/exchanges` — svuota tutti i dati (per ricominciare una sessione di test pulita).
  - `GET /api/export` — esporta exchange. Parametri: `mode` (`session`, `range`, `all`), `session_id`, `from_ts`, `to_ts`. Restituisce il file TXT in download.
- **WebSocket endpoint:**
  - `GET /ws` — stream real-time dei nuovi exchange. Il server invia un messaggio JSON per ogni nuovo exchange completato (contiene i campi necessari per la lista: exchange_id, session_id, app_method, timestamp_start, path, duration_ms).

#### 4b. Frontend Dashboard

Single-page application in **HTML + CSS + JavaScript vanilla** (niente framework).

**Layout:**

- **Header** fisso:
  - Titolo "CAME API Sniffer".
  - Contatore exchange totali.
  - Indicatore stato WebSocket (pallino verde = connesso, rosso = disconnesso).
  - Toggle "Auto-refresh" (attivo di default): quando attivo, i nuovi exchange appaiono in cima alla lista automaticamente; quando disattivo, la lista è congelata e un badge mostra quanti nuovi exchange sono arrivati.

- **Barra di ricerca:**
  - Campo testo per **ricerca full-text** (cerca in path, request body, response body).
  - Campo **Session ID** (text input con autocomplete dalle sessioni note).
  - Campo **Metodo applicativo** (dropdown popolato dinamicamente dai metodi visti, con opzione "Tutti").
  - Campi **Da** e **A** (datetime picker per intervallo data/ora).
  - Pulsanti "Cerca" e "Reset".
  - Pulsante **"Esporta"** (dropdown con opzioni: "Esporta risultati correnti", "Esporta sessione", "Esporta intervallo", "Esporta tutto"). L'export scarica un file TXT.

- **Lista exchange:**
  - Ordinamento: **più recenti in cima**.
  - Colonne: timestamp, **session ID**, **metodo applicativo** (con colore/badge), path, durata (ms).
  - Cliccando una riga si apre il pannello dettaglio.
  - Nuovi exchange in real-time: appaiono in cima alla lista (se auto-refresh attivo).
  - Paginazione a fondo lista.

- **Pannello dettaglio** (apertura a destra o sotto):
  - **Sezione Request:**
    - Metodo HTTP, URL completo.
    - Session ID, metodo applicativo.
    - Headers (collapsible, default chiuso).
    - Body con syntax highlighting JSON (pretty-printed).
  - **Sezione Response:**
    - Status code.
    - Headers (collapsible, default chiuso).
    - Body con syntax highlighting JSON (pretty-printed).
  - **Azioni:**
    - Pulsante **"Copia come cURL"** — genera il comando curl equivalente alla request.
    - Pulsante **"Esporta come TXT"** — scarica un file `.txt` contenente request e response formattate leggibilmente con separatore, inclusi headers. Formato:

```
════════════════════════════════════════════════════════════════
EXCHANGE: {exchange_id}
SESSION:  {session_id}
METHOD:   {app_method}
TIME:     {timestamp_start} → {timestamp_end} ({duration_ms}ms)
════════════════════════════════════════════════════════════════

──── REQUEST ────────────────────────────────────────────────────
{method} {path}{query_string}

Headers:
  Content-Type: application/json
  ...

Body:
{
  "sl_appl_msg": { ... },
  ...
}

──── RESPONSE ───────────────────────────────────────────────────
Status: {status_code}

Headers:
  Content-Type: application/json
  ...

Body:
{
  ...
}

════════════════════════════════════════════════════════════════
```

**Stile:** Pulito, scuro (dark theme), monospaced per headers e body. Stile ispirato a Chrome DevTools o Postman.

---

## Configurazione

File `.env` nella root del progetto:

```env
# Server CAME target
CAME_HOST=192.168.x.x
CAME_PORT=80

# Proxy (deve essere 80 per compatibilità con l'app CAME)
PROXY_PORT=80

# Dashboard
DASHBOARD_PORT=8081

# Storage
DATA_DIR=./data
DB_NAME=came_proxy.db

# Logging
LOG_LEVEL=DEBUG
```

Tutte le variabili devono avere valori di default sensati, in modo che il proxy funzioni anche senza il file `.env`.

**Nota sulla porta 80:** il container Docker deve mappare la porta 80 dell'host alla porta 80 del container. Su macOS potrebbe essere necessario fermare eventuali altri servizi sulla porta 80 o eseguire il container con privilegi adeguati.

---

## Devcontainer

### `devcontainer.json`

```json
{
  "name": "CAME API Sniffer",
  "build": {
    "dockerfile": "Dockerfile"
  },
  "forwardPorts": [80, 8081],
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-python.pylint",
        "charliermarsh.ruff"
      ]
    }
  },
  "postCreateCommand": "pip install -r requirements.txt",
  "runArgs": ["--network=host"]
}
```

**Nota su `--network=host`:** necessario affinché il container sia raggiungibile direttamente sulla LAN dall'app Android. Senza questo flag, il container sarebbe isolato nella rete Docker e l'app non potrebbe raggiungerlo. Su macOS Docker Desktop ha limitazioni con `--network=host`; se non funziona, usare il port mapping esplicito e assicurarsi che le porte siano esposte.

### `Dockerfile`

- Base image: **`python:3.14-slim`** (o `python:3.14-rc-slim` se la 3.14 stabile non è ancora disponibile al momento dell'implementazione).
- Working directory: `/workspace`
- Copiare `requirements.txt` e installare dipendenze.
- Non serve `CMD` perché il devcontainer è interattivo.

### `requirements.txt`

```
aiohttp>=3.11
aiosqlite>=0.21
python-dotenv>=1.1
```

---

## Struttura del progetto

```
came-api-sniffer/
├── .devcontainer/
│   ├── devcontainer.json
│   └── Dockerfile
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point, avvia proxy e dashboard
│   ├── config.py             # Carica configurazione da .env
│   ├── proxy.py              # Reverse proxy core
│   ├── storage.py            # Storage layer (JSON + SQLite)
│   ├── export.py             # Export exchange (TXT)
│   ├── dashboard.py          # Dashboard backend (REST + WebSocket)
│   └── static/
│       ├── index.html         # Dashboard SPA
│       ├── style.css          # Dark theme
│       └── app.js             # Logica frontend
├── data/                      # Creata automaticamente
│   ├── exchanges/             # File JSON
│   ├── exports/               # File TXT esportati
│   └── came_proxy.db          # SQLite DB
├── .env.example               # Template configurazione
├── .env                       # Configurazione attiva (gitignored)
├── requirements.txt
├── README.md                  # Istruzioni setup e uso
└── .gitignore
```

---

## Git e GitHub

Il progetto va sotto version control. Il file `.gitignore` deve includere:

```gitignore
# Configurazione locale
.env

# Dati runtime
data/

# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/

# IDE
.vscode/
!.vscode/settings.json
*.swp
*.swo

# macOS
.DS_Store
```

---

## Istruzioni operative (README)

Il README deve contenere:

1. **Prerequisiti**: Docker, VSCode con estensione Dev Containers.
2. **Setup**:
   - Clonare il repo.
   - Copiare `.env.example` in `.env` e configurare `CAME_HOST` con l'IP del server CAME reale.
   - Aprire in VSCode → "Reopen in Container".
   - Avviare con `python src/main.py`.
3. **Configurazione dell'app Android**:
   - Aprire l'app CAME Domotic.
   - Nelle impostazioni dell'app, cambiare l'IP del server impostandolo all'**IP del Mac** sulla LAN (es. `192.168.1.100`).
   - L'app comunicherà col proxy (porta 80) credendo che sia il server CAME.
   - **Non** è necessario configurare alcun proxy HTTP nelle impostazioni Android.
4. **Uso dashboard**: aprire `http://localhost:8081` nel browser del Mac.
5. **Export dati**: dalla dashboard (pulsante Esporta) o via API (`GET /api/export?mode=all`).
6. **Analisi dati con Claude Code**: i file JSON sono in `data/exchanges/`, il DB SQLite è `data/came_proxy.db`. Per interrogare il DB direttamente: `sqlite3 data/came_proxy.db "SELECT * FROM exchanges WHERE session_id = 'xxx'"`.

---

## Note implementative

- **Async everywhere**: il proxy deve essere completamente asincrono (aiohttp + aiosqlite). Nessuna operazione bloccante nel loop.
- **Robustezza**: il proxy non deve mai crashare a causa di una singola request malformata o di un errore di storage. Loggare l'errore e continuare. Se il body non è JSON valido, i campi `session_id` e `app_method` saranno `null`.
- **Performance**: per i volumi previsti (~5 req/min) non servono ottimizzazioni particolari, ma il salvataggio su DB e file deve avvenire in modo non bloccante rispetto al forwarding della response.
- **Encoding**: gestire correttamente i body con encoding diversi (UTF-8 è il default atteso, ma non assumere).
- **Headers hop-by-hop**: rimuovere/non propagare gli headers hop-by-hop standard (Connection, Keep-Alive, Transfer-Encoding, ecc.) quando si inoltra la request/response.
- **Content-Length**: ricalcolare se necessario dopo eventuali modifiche agli headers.
- **Graceful shutdown**: su SIGINT/SIGTERM, completare gli exchange in corso, chiudere le connessioni al DB, e poi uscire.
- **Porta 80**: il proxy deve ascoltare sulla porta 80. Documentare nel README eventuali problemi di permessi (su Linux serve `CAP_NET_BIND_SERVICE` o esecuzione come root; in Docker la porta è mappata dal container).
