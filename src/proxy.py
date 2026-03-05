"""Reverse proxy module for CAME API Sniffer.

Implements HTTP reverse proxy that intercepts requests, forwards them to the
CAME server, captures responses, and logs all traffic to storage.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import aiohttp
from aiohttp import web

from .config import CONFIG, LOGGER
from .storage import get_storage


class ProxyHandler:
    """HTTP reverse proxy handler."""

    def __init__(self):
        """Initialize proxy handler."""
        self.came_url = f"http://{CONFIG.came_host}:{CONFIG.came_port}"
        self.client_session: Optional[aiohttp.ClientSession] = None

    async def setup_client_session(self) -> None:
        """Set up aiohttp client session."""
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.client_session = aiohttp.ClientSession(timeout=timeout)

    async def close_client_session(self) -> None:
        """Close aiohttp client session."""
        if self.client_session:
            await self.client_session.close()

    def _extract_metadata(self, body: Any) -> tuple[Optional[str], Optional[str]]:
        """Extract session_id and app_method from JSON body.

        Args:
            body: Request body (dict or None).

        Returns:
            Tuple of (session_id, app_method), both None if parsing fails.
        """
        if not isinstance(body, dict):
            return None, None

        try:
            session_id = body.get("sl_client_id")

            # Try primary method
            app_method = None
            if "sl_appl_msg" in body and isinstance(body["sl_appl_msg"], dict):
                app_method = body["sl_appl_msg"].get("cmd_name")

            # Fallback to sl_cmd if no cmd_name
            if not app_method:
                app_method = body.get("sl_cmd")

            return session_id, app_method

        except Exception:
            return None, None

    def _parse_request_body(self, raw_body: bytes) -> tuple[Any, bool]:
        """Parse request body as JSON if possible.

        Args:
            raw_body: Raw body bytes.

        Returns:
            Tuple of (parsed_body, is_json).
            - If valid JSON: returns parsed dict and True.
            - If invalid JSON: returns raw string and False.
            - If empty: returns None and False.
        """
        if not raw_body:
            return None, False

        try:
            body = json.loads(raw_body.decode("utf-8"))
            return body, True
        except (json.JSONDecodeError, UnicodeDecodeError):
            try:
                return raw_body.decode("utf-8"), False
            except UnicodeDecodeError:
                return str(raw_body), False

    def _filter_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Filter out hop-by-hop headers.

        Args:
            headers: Original headers.

        Returns:
            Filtered headers.
        """
        # Hop-by-hop headers to remove
        hop_by_hop = {
            "connection",
            "keep-alive",
            "transfer-encoding",
            "upgrade",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
        }

        filtered = {}
        for key, value in headers.items():
            if key.lower() not in hop_by_hop:
                filtered[key] = value

        return filtered

    async def handle_request(
        self, request: web.Request
    ) -> web.StreamResponse:
        """Handle incoming HTTP request.

        Args:
            request: aiohttp request object.

        Returns:
            aiohttp response object.
        """
        exchange_id = str(uuid4())
        timestamp_start = datetime.now(timezone.utc).replace(tzinfo=None)
        storage = await get_storage()

        try:
            # Read request body
            raw_body = await request.read()
            parsed_body, is_json = self._parse_request_body(raw_body)

            # Extract metadata
            session_id, app_method = self._extract_metadata(
                parsed_body if is_json else None
            )

            # Build request data
            request_headers = dict(request.headers)
            request_data = {
                "method": request.method,
                "path": request.path,
                "query_string": request.query_string,
                "headers": self._filter_headers(request_headers),
                "body": parsed_body if is_json else raw_body.decode("utf-8", errors="replace"),
            }

            # Save request to storage
            exchange_data = {
                "exchange_id": exchange_id,
                "session_id": session_id,
                "app_method": app_method,
                "timestamp_start": timestamp_start.isoformat() + "Z",
                "request": request_data,
            }

            await storage.save_request(exchange_data)
            LOGGER.info(
                f"[{exchange_id}] Request: {request.method} {request.path} "
                f"(session={session_id}, method={app_method})"
            )

            # Forward request to CAME server
            forward_url = self.came_url + request.path
            if request.query_string:
                forward_url += "?" + request.query_string

            # Prepare headers for forwarding (remove Host, add new one)
            forward_headers = self._filter_headers(dict(request.headers))
            forward_headers["Host"] = f"{CONFIG.came_host}:{CONFIG.came_port}"

            # Forward request
            try:
                async with self.client_session.request(
                    request.method,
                    forward_url,
                    data=raw_body if raw_body else None,
                    headers=forward_headers,
                    allow_redirects=False,
                ) as came_response:
                    response_body = await came_response.read()

                    # Parse response body
                    response_parsed, response_is_json = self._parse_request_body(response_body)

                    timestamp_end = datetime.now(timezone.utc).replace(tzinfo=None)
                    duration_ms = int(
                        (timestamp_end - timestamp_start).total_seconds() * 1000
                    )

                    # Save response to storage
                    response_data = {
                        "status_code": came_response.status,
                        "headers": dict(came_response.headers),
                        "body": response_parsed if response_is_json else response_body.decode("utf-8", errors="replace"),
                        "timestamp_end": timestamp_end.isoformat() + "Z",
                        "duration_ms": duration_ms,
                    }

                    await storage.save_response(exchange_id, response_data)
                    LOGGER.info(
                        f"[{exchange_id}] Response: {came_response.status} "
                        f"({duration_ms}ms)"
                    )

                    # Return response to client
                    response = web.StreamResponse(
                        status=came_response.status,
                        headers=self._filter_headers(dict(came_response.headers)),
                    )
                    await response.prepare(request)
                    await response.write(response_body)
                    await response.write_eof()
                    return response

            except asyncio.TimeoutError:
                error_msg = "Gateway timeout"
                await storage.save_error(exchange_id, error_msg)
                LOGGER.error(f"[{exchange_id}] {error_msg}")
                return web.Response(status=504, text=error_msg)

            except (aiohttp.ClientConnectionError, aiohttp.ClientError) as e:
                error_msg = f"Bad gateway: {str(e)}"
                await storage.save_error(exchange_id, error_msg)
                LOGGER.error(f"[{exchange_id}] {error_msg}")
                return web.Response(status=502, text=error_msg)

        except Exception as e:
            error_msg = f"Proxy error: {str(e)}"
            LOGGER.error(f"[{exchange_id}] {error_msg}", exc_info=True)
            try:
                await storage.save_error(exchange_id, error_msg)
            except Exception:
                pass
            return web.Response(status=502, text=error_msg)


async def create_proxy_app(proxy_handler: ProxyHandler) -> web.Application:
    """Create aiohttp proxy application.

    Args:
        proxy_handler: ProxyHandler instance.

    Returns:
        aiohttp Application.
    """
    app = web.Application()

    # Catch-all route for proxy
    app.router.add_route("*", "/{path_info:.*}", proxy_handler.handle_request)

    # Setup cleanup
    async def on_startup(app):
        await proxy_handler.setup_client_session()

    async def on_cleanup(app):
        await proxy_handler.close_client_session()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    return app


# Import asyncio for timeout handling
import asyncio
