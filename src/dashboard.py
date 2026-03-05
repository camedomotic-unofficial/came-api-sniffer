"""Dashboard module for CAME API Sniffer.

Implements REST API endpoints and WebSocket server for the web dashboard.
"""

import asyncio
import json
from typing import Any, Optional, Set
from pathlib import Path

from aiohttp import web

from .config import CONFIG, LOGGER
from .storage import get_storage
from .export import get_exporter


class DashboardBackend:
    """Dashboard backend with REST API and WebSocket support."""

    def __init__(self):
        """Initialize dashboard backend."""
        self.static_dir = Path(__file__).parent / "static"
        self.websocket_clients: Set[web.WebSocketResponse] = set()

    async def handle_index(self, request: web.Request) -> web.Response:
        """Serve index.html.

        Args:
            request: aiohttp request.

        Returns:
            aiohttp response.
        """
        index_path = self.static_dir / "index.html"
        if index_path.exists():
            with open(index_path, "r") as f:
                return web.Response(text=f.read(), content_type="text/html")
        return web.Response(text="Dashboard UI not found", status=404)

    async def handle_static(self, request: web.Request) -> web.Response:
        """Serve static files (CSS, JS).

        Args:
            request: aiohttp request.

        Returns:
            aiohttp response.
        """
        file_path = request.match_info["filename"]
        full_path = self.static_dir / file_path

        if not full_path.exists() or not full_path.is_file():
            return web.Response(text="File not found", status=404)

        content_type = "text/css" if file_path.endswith(".css") else "application/javascript"
        with open(full_path, "r") as f:
            return web.Response(text=f.read(), content_type=content_type)

    async def api_get_exchanges(self, request: web.Request) -> web.Response:
        """GET /api/exchanges - List exchanges with pagination and filters.

        Query parameters:
            - page: Page number (default 1)
            - page_size: Results per page (default 20)
            - search: Full-text search
            - session_id: Filter by session ID
            - app_method: Filter by app method
            - from_ts: Start timestamp
            - to_ts: End timestamp

        Returns:
            JSON with exchanges and pagination info.
        """
        try:
            storage = await get_storage()

            page = int(request.rel_url.query.get("page", 1))
            page_size = int(request.rel_url.query.get("page_size", 100))
            search = request.rel_url.query.get("search")
            session_id = request.rel_url.query.get("session_id")
            app_method = request.rel_url.query.get("app_method")
            from_ts = request.rel_url.query.get("from_ts")
            to_ts = request.rel_url.query.get("to_ts")

            exchanges, total_count = await storage.query_exchanges(
                page=page,
                page_size=page_size,
                search=search,
                session_id=session_id,
                app_method=app_method,
                from_ts=from_ts,
                to_ts=to_ts,
            )

            return web.json_response({
                "exchanges": exchanges,
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": (total_count + page_size - 1) // page_size,
            })

        except Exception as e:
            LOGGER.error(f"Error getting exchanges: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_get_exchange(self, request: web.Request) -> web.Response:
        """GET /api/exchanges/{exchange_id} - Get single exchange.

        Args:
            request: aiohttp request.

        Returns:
            JSON with exchange data.
        """
        try:
            exchange_id = request.match_info["exchange_id"]
            storage = await get_storage()
            exchange = await storage.get_exchange(exchange_id)

            if not exchange:
                return web.json_response({"error": "Exchange not found"}, status=404)

            return web.json_response(exchange)

        except Exception as e:
            LOGGER.error(f"Error getting exchange: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_get_sessions(self, request: web.Request) -> web.Response:
        """GET /api/sessions - Get distinct sessions.

        Returns:
            JSON list of sessions with counts.
        """
        try:
            storage = await get_storage()
            sessions = await storage.get_distinct_sessions()
            return web.json_response({"sessions": sessions})

        except Exception as e:
            LOGGER.error(f"Error getting sessions: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_get_methods(self, request: web.Request) -> web.Response:
        """GET /api/methods - Get distinct app methods.

        Returns:
            JSON list of methods with counts.
        """
        try:
            storage = await get_storage()
            methods = await storage.get_distinct_methods()
            return web.json_response({"methods": methods})

        except Exception as e:
            LOGGER.error(f"Error getting methods: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_get_stats(self, request: web.Request) -> web.Response:
        """GET /api/stats - Get aggregate statistics.

        Returns:
            JSON with statistics.
        """
        try:
            storage = await get_storage()
            stats = await storage.get_statistics()
            return web.json_response(stats)

        except Exception as e:
            LOGGER.error(f"Error getting stats: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_delete_exchanges(self, request: web.Request) -> web.Response:
        """DELETE /api/exchanges - Delete all exchanges.

        Returns:
            JSON confirmation.
        """
        try:
            storage = await get_storage()
            await storage.delete_all_exchanges()
            return web.json_response({"status": "success", "message": "All exchanges deleted"})

        except Exception as e:
            LOGGER.error(f"Error deleting exchanges: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_export(self, request: web.Request) -> web.Response:
        """GET /api/export - Export exchanges.

        Query parameters:
            - mode: 'all', 'session', or 'range'
            - session_id: Session ID (for mode=session)
            - from_ts: Start timestamp (for mode=range)
            - to_ts: End timestamp (for mode=range)

        Returns:
            TXT file download.
        """
        try:
            exporter = await get_exporter()
            mode = request.rel_url.query.get("mode", "all")

            if mode == "session":
                session_id = request.rel_url.query.get("session_id")
                if not session_id:
                    return web.json_response(
                        {"error": "session_id required for mode=session"}, status=400
                    )
                exclude_method = request.rel_url.query.get("exclude_method")
                filepath = await exporter.export_session(session_id, exclude_method=exclude_method)
            elif mode == "range":
                from_ts = request.rel_url.query.get("from_ts")
                to_ts = request.rel_url.query.get("to_ts")
                if not from_ts or not to_ts:
                    return web.json_response(
                        {"error": "from_ts and to_ts required for mode=range"}, status=400
                    )
                filepath = await exporter.export_range(from_ts, to_ts)
            else:  # mode == "all"
                filepath = await exporter.export_all()

            with open(filepath, "r") as f:
                content = f.read()

            return web.Response(
                text=content,
                content_type="text/plain",
                headers={"Content-Disposition": f"attachment; filename={filepath.name}"},
            )

        except Exception as e:
            LOGGER.error(f"Error exporting: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_delete_exchange(self, request: web.Request) -> web.Response:
        """DELETE /api/exchanges/{exchange_id} - Delete a single exchange.

        Returns:
            JSON confirmation.
        """
        try:
            exchange_id = request.match_info["exchange_id"]
            storage = await get_storage()
            deleted = await storage.delete_exchange(exchange_id)
            if not deleted:
                return web.json_response(
                    {"error": "Exchange not found"}, status=404
                )
            return web.json_response({
                "status": "success",
                "message": f"Deleted exchange {exchange_id}",
            })

        except Exception as e:
            LOGGER.error(f"Error deleting exchange: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_delete_session(self, request: web.Request) -> web.Response:
        """DELETE /api/sessions/{session_id} - Delete all exchanges for a session.

        Returns:
            JSON confirmation with count of deleted exchanges.
        """
        try:
            session_id = request.match_info["session_id"]
            storage = await get_storage()
            count = await storage.delete_session_exchanges(session_id)
            return web.json_response({
                "status": "success",
                "message": f"Deleted {count} exchanges for session {session_id}",
                "deleted_count": count,
            })

        except Exception as e:
            LOGGER.error(f"Error deleting session: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_set_session_annotation(self, request: web.Request) -> web.Response:
        """PUT /api/sessions/{session_id}/annotation - Set session annotation."""
        try:
            session_id = request.match_info["session_id"]
            body = await request.json()
            name = body.get("name")
            notes = body.get("notes")

            storage = await get_storage()
            result = await storage.set_session_annotation(session_id, name, notes)
            return web.json_response(result)

        except Exception as e:
            LOGGER.error(f"Error setting session annotation: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_delete_session_annotation(self, request: web.Request) -> web.Response:
        """DELETE /api/sessions/{session_id}/annotation - Delete session annotation."""
        try:
            session_id = request.match_info["session_id"]
            storage = await get_storage()
            await storage.delete_session_annotation(session_id)
            return web.json_response({"status": "success"})

        except Exception as e:
            LOGGER.error(f"Error deleting session annotation: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """WebSocket endpoint /ws - Stream real-time exchange updates.

        Args:
            request: aiohttp request.

        Returns:
            WebSocket response.
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.websocket_clients.add(ws)
        LOGGER.info(f"WebSocket client connected. Total: {len(self.websocket_clients)}")

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.ERROR:
                    LOGGER.error(f"WebSocket error: {ws.exception()}")
        finally:
            self.websocket_clients.discard(ws)
            LOGGER.info(f"WebSocket client disconnected. Total: {len(self.websocket_clients)}")

        return ws

    async def broadcast_exchange(self, exchange: dict[str, Any]) -> None:
        """Broadcast new exchange to all WebSocket clients.

        Args:
            exchange: Exchange data to broadcast.
        """
        message = json.dumps({
            "type": "new_exchange",
            "exchange_id": exchange.get("exchange_id"),
            "session_id": exchange.get("session_id"),
            "app_method": exchange.get("app_method"),
            "timestamp_start": exchange.get("timestamp_start"),
            "path": exchange.get("path"),
            "duration_ms": exchange.get("duration_ms"),
            "status_code": exchange.get("status_code"),
        })

        disconnected = set()
        for ws in self.websocket_clients:
            try:
                if not ws.closed:
                    await ws.send_str(message)
            except Exception as e:
                LOGGER.warning(f"Error broadcasting to client: {e}")
                disconnected.add(ws)

        # Remove disconnected clients
        for ws in disconnected:
            self.websocket_clients.discard(ws)


async def create_dashboard_app(dashboard: DashboardBackend) -> web.Application:
    """Create aiohttp dashboard application.

    Args:
        dashboard: DashboardBackend instance.

    Returns:
        aiohttp Application.
    """
    app = web.Application()

    # Routes
    app.router.add_get("/", dashboard.handle_index)
    app.router.add_get("/static/{filename}", dashboard.handle_static)

    # API routes
    app.router.add_get("/api/exchanges", dashboard.api_get_exchanges)
    app.router.add_get("/api/exchanges/{exchange_id}", dashboard.api_get_exchange)
    app.router.add_get("/api/sessions", dashboard.api_get_sessions)
    app.router.add_get("/api/methods", dashboard.api_get_methods)
    app.router.add_get("/api/stats", dashboard.api_get_stats)
    app.router.add_delete("/api/exchanges", dashboard.api_delete_exchanges)
    app.router.add_delete("/api/exchanges/{exchange_id}", dashboard.api_delete_exchange)
    app.router.add_delete("/api/sessions/{session_id}", dashboard.api_delete_session)
    app.router.add_put("/api/sessions/{session_id}/annotation", dashboard.api_set_session_annotation)
    app.router.add_delete("/api/sessions/{session_id}/annotation", dashboard.api_delete_session_annotation)
    app.router.add_get("/api/export", dashboard.api_export)

    # WebSocket
    app.router.add_get("/ws", dashboard.handle_websocket)

    return app


# Global dashboard instance
dashboard_instance: Optional[DashboardBackend] = None


async def get_dashboard() -> DashboardBackend:
    """Get or create global dashboard instance.

    Returns:
        DashboardBackend: Global instance.
    """
    global dashboard_instance
    if dashboard_instance is None:
        dashboard_instance = DashboardBackend()
    return dashboard_instance


# Import aiohttp for type hints
import aiohttp
