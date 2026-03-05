"""Storage module for CAME API Sniffer.

Implements dual storage system (JSON files + SQLite database) for exchanges.
Provides unified interface for saving and querying exchanges.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import aiosqlite

from .config import CONFIG, LOGGER


class StorageManager:
    """Unified storage interface for JSON files and SQLite database."""

    def __init__(self):
        """Initialize storage manager."""
        self.data_dir = Path(CONFIG.data_dir)
        self.exchanges_dir = self.data_dir / "exchanges"
        self.exports_dir = self.data_dir / "exports"
        self.db_path = self.data_dir / CONFIG.db_name

        # Create directories
        self.data_dir.mkdir(exist_ok=True)
        self.exchanges_dir.mkdir(exist_ok=True)
        self.exports_dir.mkdir(exist_ok=True)

        self.db: Optional[aiosqlite.Connection] = None

    async def init_db(self) -> None:
        """Initialize SQLite database and create schema.

        Creates tables and indexes if they don't exist.
        """
        self.db = await aiosqlite.connect(str(self.db_path))
        self.db.row_factory = aiosqlite.Row

        # Enable WAL mode for better concurrency
        await self.db.execute("PRAGMA journal_mode=WAL")

        # Create main exchanges table
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS exchanges (
                exchange_id      TEXT PRIMARY KEY,
                session_id       TEXT,
                app_method       TEXT,
                timestamp_start  TEXT NOT NULL,
                timestamp_end    TEXT,
                duration_ms      INTEGER,
                method           TEXT NOT NULL,
                path             TEXT NOT NULL,
                query_string     TEXT DEFAULT '',
                request_headers  TEXT NOT NULL,
                request_body     TEXT,
                request_body_parsed TEXT,
                status_code      INTEGER,
                response_headers TEXT,
                response_body    TEXT,
                error            TEXT,
                created_at       TEXT DEFAULT (datetime('now'))
            )
            """
        )

        # Create indexes
        await self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_timestamp ON exchanges(timestamp_start)"
        )
        await self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_id ON exchanges(session_id)"
        )
        await self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_app_method ON exchanges(app_method)"
        )
        await self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_path ON exchanges(path)"
        )

        # Migration: add request_body_parsed column if missing (for existing DBs)
        try:
            await self.db.execute(
                "ALTER TABLE exchanges ADD COLUMN request_body_parsed TEXT"
            )
            await self.db.commit()
            LOGGER.info("Migrated database: added request_body_parsed column")
        except (aiosqlite.OperationalError, sqlite3.OperationalError):
            pass  # Column already exists

        # Create FTS5 virtual table for full-text search
        try:
            await self.db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS exchanges_fts USING fts5(
                    exchange_id,
                    session_id,
                    app_method,
                    path,
                    request_body_parsed,
                    response_body,
                    content='exchanges',
                    content_rowid='rowid'
                )
                """
            )

            # Create triggers to keep FTS in sync
            await self.db.execute(
                """
                CREATE TRIGGER IF NOT EXISTS exchanges_ai AFTER INSERT ON exchanges BEGIN
                    INSERT INTO exchanges_fts(rowid, exchange_id, session_id, app_method, path, request_body_parsed, response_body)
                    VALUES (new.rowid, new.exchange_id, new.session_id, new.app_method, new.path, new.request_body_parsed, new.response_body);
                END
                """
            )

            await self.db.execute(
                """
                CREATE TRIGGER IF NOT EXISTS exchanges_ad AFTER DELETE ON exchanges BEGIN
                    INSERT INTO exchanges_fts(exchanges_fts, rowid, exchange_id, session_id, app_method, path, request_body_parsed, response_body)
                    VALUES('delete', old.rowid, old.exchange_id, old.session_id, old.app_method, old.path, old.request_body_parsed, old.response_body);
                END
                """
            )

            await self.db.execute(
                """
                CREATE TRIGGER IF NOT EXISTS exchanges_au AFTER UPDATE ON exchanges BEGIN
                    INSERT INTO exchanges_fts(exchanges_fts, rowid, exchange_id, session_id, app_method, path, request_body_parsed, response_body)
                    VALUES('delete', old.rowid, old.exchange_id, old.session_id, old.app_method, old.path, old.request_body_parsed, old.response_body);
                    INSERT INTO exchanges_fts(rowid, exchange_id, session_id, app_method, path, request_body_parsed, response_body)
                    VALUES(new.rowid, new.exchange_id, new.session_id, new.app_method, new.path, new.request_body_parsed, new.response_body);
                END
                """
            )
        except aiosqlite.OperationalError as e:
            LOGGER.warning(f"FTS5 setup warning: {e}")

        # Create session_annotations table
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS session_annotations (
                session_id  TEXT PRIMARY KEY,
                name        TEXT,
                notes       TEXT,
                updated_at  TEXT DEFAULT (datetime('now'))
            )
            """
        )

        await self.db.commit()
        LOGGER.info(f"Database initialized at {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self.db:
            await self.db.close()

    def _generate_exchange_id(self) -> str:
        """Generate unique exchange ID.

        Returns:
            str: UUID v4 string.
        """
        return str(uuid4())

    def _format_timestamp(self, dt: datetime) -> str:
        """Format datetime to ISO 8601 string.

        Args:
            dt: datetime object.

        Returns:
            str: ISO 8601 formatted string.
        """
        return dt.isoformat() + "Z"

    def _generate_filename(
        self, session_id: Optional[str], timestamp: datetime, exchange_id: str
    ) -> str:
        """Generate JSON filename.

        Args:
            session_id: Session ID or None.
            timestamp: Request timestamp.
            exchange_id: Exchange UUID.

        Returns:
            str: Filename in format {session_id}_{timestamp}_{exchange_id_short}.json
        """
        session = session_id if session_id else "no-session"
        timestamp_str = timestamp.strftime("%Y%m%d-%H%M%S") + f"-{timestamp.microsecond // 1000:03d}"
        exchange_short = exchange_id[:8]
        return f"{session}_{timestamp_str}_{exchange_short}.json"

    async def save_request(self, exchange_data: dict[str, Any]) -> str:
        """Save request to both JSON file and SQLite database.

        Args:
            exchange_data: Exchange data dictionary with request info.

        Returns:
            str: Exchange ID.

        Raises:
            ValueError: If exchange_data is invalid.
        """
        try:
            exchange_id = exchange_data["exchange_id"]
            session_id = exchange_data.get("session_id")
            app_method = exchange_data.get("app_method")
            timestamp_start = datetime.fromisoformat(
                exchange_data["timestamp_start"].rstrip("Z")
            )
            request = exchange_data["request"]

            # Convert headers to JSON string
            request_headers = json.dumps(request.get("headers", {}))
            request_body = request.get("body", "")  # raw body string
            request_body_parsed = request.get("body_parsed")
            if isinstance(request_body_parsed, dict):
                request_body_parsed = json.dumps(request_body_parsed)

            # Save to SQLite
            await self.db.execute(
                """
                INSERT INTO exchanges (
                    exchange_id, session_id, app_method, timestamp_start,
                    method, path, query_string, request_headers, request_body,
                    request_body_parsed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exchange_id,
                    session_id,
                    app_method,
                    exchange_data["timestamp_start"],
                    request["method"],
                    request["path"],
                    request.get("query_string", ""),
                    request_headers,
                    request_body,
                    request_body_parsed,
                ),
            )
            await self.db.commit()

            # Save to JSON file
            filename = self._generate_filename(session_id, timestamp_start, exchange_id)
            filepath = self.exchanges_dir / filename
            with open(filepath, "w") as f:
                json.dump(exchange_data, f, indent=2)

            LOGGER.debug(f"Saved request for exchange {exchange_id}")
            return exchange_id

        except Exception as e:
            LOGGER.error(f"Error saving request: {e}")
            raise

    async def save_response(
        self, exchange_id: str, response_data: dict[str, Any]
    ) -> None:
        """Update exchange with response data.

        Args:
            exchange_id: Exchange ID.
            response_data: Response data dictionary.
        """
        try:
            # Convert headers to JSON string
            response_headers = json.dumps(response_data.get("headers", {}))
            response_body = response_data.get("body")
            if isinstance(response_body, dict):
                response_body = json.dumps(response_body)

            # Update SQLite
            await self.db.execute(
                """
                UPDATE exchanges
                SET timestamp_end = ?, duration_ms = ?, status_code = ?,
                    response_headers = ?, response_body = ?
                WHERE exchange_id = ?
                """,
                (
                    response_data["timestamp_end"],
                    response_data.get("duration_ms"),
                    response_data["status_code"],
                    response_headers,
                    response_body,
                    exchange_id,
                ),
            )
            await self.db.commit()

            # Update JSON file
            # Find the file for this exchange
            for filepath in self.exchanges_dir.glob("*" + exchange_id[:8] + ".json"):
                with open(filepath, "r") as f:
                    data = json.load(f)
                data["timestamp_end"] = response_data["timestamp_end"]
                data["duration_ms"] = response_data.get("duration_ms")
                data["response"] = {
                    "status_code": response_data["status_code"],
                    "headers": response_data.get("headers", {}),
                    "body": response_data.get("body"),
                }
                with open(filepath, "w") as f:
                    json.dump(data, f, indent=2)
                break

            LOGGER.debug(f"Saved response for exchange {exchange_id}")

        except Exception as e:
            LOGGER.error(f"Error saving response: {e}")
            raise

    async def update_session_id(
        self, exchange_id: str, session_id: str, timestamp_start: datetime
    ) -> None:
        """Update session_id for an exchange (e.g. after login response reveals it).

        Updates SQLite, JSON file content, and renames the JSON file to reflect
        the new session_id.

        Args:
            exchange_id: Exchange ID.
            session_id: New session ID to set.
            timestamp_start: Request timestamp (needed for filename generation).
        """
        try:
            # Update SQLite
            await self.db.execute(
                "UPDATE exchanges SET session_id = ? WHERE exchange_id = ?",
                (session_id, exchange_id),
            )
            await self.db.commit()

            # Update and rename JSON file
            for filepath in self.exchanges_dir.glob("*" + exchange_id[:8] + ".json"):
                with open(filepath, "r") as f:
                    data = json.load(f)
                data["session_id"] = session_id

                # Write updated content to new filename
                new_filename = self._generate_filename(
                    session_id, timestamp_start, exchange_id
                )
                new_filepath = self.exchanges_dir / new_filename
                with open(new_filepath, "w") as f:
                    json.dump(data, f, indent=2)

                # Remove old file if name changed
                if filepath != new_filepath:
                    filepath.unlink()

                break

            LOGGER.debug(
                f"Updated session_id to {session_id} for exchange {exchange_id}"
            )

        except Exception as e:
            LOGGER.error(f"Error updating session_id: {e}")

    async def save_error(self, exchange_id: str, error_msg: str) -> None:
        """Save error information for an exchange.

        Args:
            exchange_id: Exchange ID.
            error_msg: Error message.
        """
        try:
            await self.db.execute(
                "UPDATE exchanges SET error = ? WHERE exchange_id = ?",
                (error_msg, exchange_id),
            )
            await self.db.commit()

            # Update JSON file
            for filepath in self.exchanges_dir.glob("*" + exchange_id[:8] + ".json"):
                with open(filepath, "r") as f:
                    data = json.load(f)
                data["error"] = error_msg
                with open(filepath, "w") as f:
                    json.dump(data, f, indent=2)
                break

        except Exception as e:
            LOGGER.error(f"Error saving error: {e}")

    async def query_exchanges(
        self,
        page: int = 1,
        page_size: int = 100,
        search: Optional[str] = None,
        session_id: Optional[str] = None,
        app_method: Optional[str] = None,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query exchanges with filters.

        Args:
            page: Page number (1-indexed).
            page_size: Results per page.
            search: Full-text search query.
            session_id: Filter by session ID.
            app_method: Filter by app method.
            from_ts: Start timestamp (ISO 8601).
            to_ts: End timestamp (ISO 8601).

        Returns:
            Tuple of (exchanges list, total count).
        """
        try:
            where_clauses = []
            params: list[Any] = []

            if search:
                # Use FTS5 for search
                fts_query = f"SELECT rowid FROM exchanges_fts WHERE exchanges_fts MATCH ?"
                params.append(search)
                where_clauses.append(f"rowid IN ({fts_query})")
            else:
                params.clear()

            if session_id:
                where_clauses.append("session_id = ?")
                params.append(session_id)

            if app_method:
                where_clauses.append("app_method = ?")
                params.append(app_method)

            if from_ts:
                where_clauses.append("timestamp_start >= ?")
                params.append(from_ts)

            if to_ts:
                where_clauses.append("timestamp_start <= ?")
                params.append(to_ts)

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Get total count
            count_query = f"SELECT COUNT(*) as count FROM exchanges WHERE {where_clause}"
            cursor = await self.db.execute(count_query, params)
            result = await cursor.fetchone()
            total_count = result["count"] if result else 0

            # Get paginated results
            offset = (page - 1) * page_size
            query = f"""
                SELECT exchange_id, session_id, app_method, timestamp_start,
                       timestamp_end, duration_ms, method, status_code
                FROM exchanges
                WHERE {where_clause}
                ORDER BY timestamp_start DESC
                LIMIT ? OFFSET ?
            """
            params.extend([page_size, offset])

            cursor = await self.db.execute(query, params)
            rows = await cursor.fetchall()

            exchanges = [dict(row) for row in rows]
            return exchanges, total_count

        except Exception as e:
            LOGGER.error(f"Error querying exchanges: {e}")
            raise

    async def get_exchange(self, exchange_id: str) -> Optional[dict[str, Any]]:
        """Get single exchange by ID.

        Args:
            exchange_id: Exchange ID.

        Returns:
            Exchange data or None if not found.
        """
        try:
            cursor = await self.db.execute(
                "SELECT * FROM exchanges WHERE exchange_id = ?", (exchange_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None

            exchange = dict(row)

            # Parse JSON fields
            try:
                exchange["request_headers"] = json.loads(
                    exchange["request_headers"] or "{}"
                )
            except json.JSONDecodeError:
                exchange["request_headers"] = {}

            try:
                exchange["response_headers"] = json.loads(
                    exchange["response_headers"] or "{}"
                )
            except json.JSONDecodeError:
                exchange["response_headers"] = {}

            # request_body stays as raw string (e.g. "command={...}")

            try:
                if exchange.get("request_body_parsed"):
                    exchange["request_body_parsed"] = json.loads(exchange["request_body_parsed"])
            except (json.JSONDecodeError, TypeError):
                pass

            try:
                if exchange["response_body"]:
                    exchange["response_body"] = json.loads(exchange["response_body"])
            except (json.JSONDecodeError, TypeError):
                pass

            return exchange

        except Exception as e:
            LOGGER.error(f"Error getting exchange: {e}")
            raise

    async def get_distinct_sessions(self) -> list[dict[str, Any]]:
        """Get distinct sessions with exchange counts.

        Returns:
            List of dicts with session_id and count.
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT e.session_id, COUNT(*) as count,
                       sa.name as session_name, sa.notes as session_notes
                FROM exchanges e
                LEFT JOIN session_annotations sa ON e.session_id = sa.session_id
                WHERE e.session_id IS NOT NULL
                GROUP BY e.session_id
                ORDER BY e.session_id
                """
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            LOGGER.error(f"Error getting sessions: {e}")
            raise

    async def get_distinct_methods(self) -> list[dict[str, Any]]:
        """Get distinct app methods with exchange counts.

        Returns:
            List of dicts with app_method and count.
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT app_method, COUNT(*) as count
                FROM exchanges
                WHERE app_method IS NOT NULL
                GROUP BY app_method
                ORDER BY app_method
                """
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            LOGGER.error(f"Error getting methods: {e}")
            raise

    async def get_statistics(self) -> dict[str, Any]:
        """Get aggregate statistics.

        Returns:
            Dictionary with statistics.
        """
        try:
            cursor = await self.db.execute(
                "SELECT COUNT(*) as total FROM exchanges"
            )
            total = (await cursor.fetchone())["total"]

            sessions = await self.get_distinct_sessions()
            methods = await self.get_distinct_methods()

            cursor = await self.db.execute(
                """
                SELECT path, COUNT(*) as count
                FROM exchanges
                GROUP BY path
                ORDER BY count DESC
                LIMIT 10
                """
            )
            top_paths = [dict(row) for row in await cursor.fetchall()]

            return {
                "total_exchanges": total,
                "distinct_sessions": len(sessions),
                "distinct_methods": len(methods),
                "top_paths": top_paths,
            }

        except Exception as e:
            LOGGER.error(f"Error getting statistics: {e}")
            raise

    async def delete_all_exchanges(self) -> None:
        """Delete all exchanges from database and remove JSON files."""
        try:
            await self.db.execute("DELETE FROM exchanges")
            await self.db.execute("DELETE FROM session_annotations")
            await self.db.commit()

            # Remove JSON files
            for filepath in self.exchanges_dir.glob("*.json"):
                filepath.unlink()

            LOGGER.info("Deleted all exchanges")

        except Exception as e:
            LOGGER.error(f"Error deleting exchanges: {e}")
            raise

    async def delete_exchange(self, exchange_id: str) -> bool:
        """Delete a single exchange by ID.

        Args:
            exchange_id: Exchange ID to delete.

        Returns:
            True if the exchange was found and deleted, False otherwise.
        """
        try:
            # Get exchange info for JSON file removal
            cursor = await self.db.execute(
                "SELECT session_id, timestamp_start FROM exchanges WHERE exchange_id = ?",
                (exchange_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return False

            session_id = row["session_id"] or "no-session"
            exchange_id_short = exchange_id[:8]

            # Delete from SQLite
            await self.db.execute(
                "DELETE FROM exchanges WHERE exchange_id = ?", (exchange_id,)
            )
            await self.db.commit()

            # Remove JSON file
            for filepath in self.exchanges_dir.glob(f"*_{exchange_id_short}.json"):
                filepath.unlink()

            LOGGER.info(f"Deleted exchange {exchange_id}")
            return True

        except Exception as e:
            LOGGER.error(f"Error deleting exchange: {e}")
            raise

    async def delete_session_exchanges(self, session_id: str) -> int:
        """Delete all exchanges for a given session ID.

        Args:
            session_id: Session ID whose exchanges should be deleted.

        Returns:
            int: Number of deleted exchanges.
        """
        try:
            # Count before delete
            cursor = await self.db.execute(
                "SELECT COUNT(*) as count FROM exchanges WHERE session_id = ?",
                (session_id,),
            )
            result = await cursor.fetchone()
            count = result["count"] if result else 0

            # Delete from SQLite
            await self.db.execute(
                "DELETE FROM exchanges WHERE session_id = ?", (session_id,)
            )
            await self.db.execute(
                "DELETE FROM session_annotations WHERE session_id = ?",
                (session_id,),
            )
            await self.db.commit()

            # Remove JSON files for this session
            for filepath in self.exchanges_dir.glob(f"{session_id}_*.json"):
                filepath.unlink()

            LOGGER.info(f"Deleted {count} exchanges for session {session_id}")
            return count

        except Exception as e:
            LOGGER.error(f"Error deleting session exchanges: {e}")
            raise

    async def set_session_annotation(
        self, session_id: str, name: Optional[str], notes: Optional[str]
    ) -> dict[str, Any]:
        """Set or update annotation for a session (upsert)."""
        try:
            await self.db.execute(
                """
                INSERT INTO session_annotations (session_id, name, notes, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(session_id) DO UPDATE SET
                    name = excluded.name,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (session_id, name, notes),
            )
            await self.db.commit()
            return {"session_id": session_id, "name": name, "notes": notes}
        except Exception as e:
            LOGGER.error(f"Error setting session annotation: {e}")
            raise

    async def get_all_session_annotations(self) -> dict[str, dict[str, Any]]:
        """Get all session annotations as a dict keyed by session_id."""
        try:
            cursor = await self.db.execute(
                "SELECT session_id, name, notes, updated_at FROM session_annotations"
            )
            rows = await cursor.fetchall()
            return {row["session_id"]: dict(row) for row in rows}
        except Exception as e:
            LOGGER.error(f"Error getting session annotations: {e}")
            raise

    async def delete_session_annotation(self, session_id: str) -> None:
        """Delete annotation for a session."""
        try:
            await self.db.execute(
                "DELETE FROM session_annotations WHERE session_id = ?",
                (session_id,),
            )
            await self.db.commit()
        except Exception as e:
            LOGGER.error(f"Error deleting session annotation: {e}")
            raise


# Global storage manager instance
storage_manager: Optional[StorageManager] = None


async def get_storage() -> StorageManager:
    """Get or create global storage manager instance.

    Returns:
        StorageManager: Global instance.
    """
    global storage_manager
    if storage_manager is None:
        storage_manager = StorageManager()
        await storage_manager.init_db()
    return storage_manager
