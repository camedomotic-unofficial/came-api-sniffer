"""Main entry point for CAME API Sniffer.

Starts the HTTP proxy and dashboard web server in a single event loop.
"""

import asyncio
import signal
from typing import Optional

import aiohttp
from aiohttp import web

from .config import CONFIG, LOGGER
from .storage import get_storage
from .proxy import ProxyHandler, create_proxy_app
from .dashboard import DashboardBackend, create_dashboard_app


async def run_servers() -> None:
    """Run proxy and dashboard servers concurrently."""
    LOGGER.info("Starting CAME API Sniffer")
    LOGGER.info(f"Proxy: http://0.0.0.0:{CONFIG.proxy_port}")
    LOGGER.info(f"Dashboard: http://0.0.0.0:{CONFIG.dashboard_port}")
    LOGGER.info(f"CAME Server: http://{CONFIG.came_host}:{CONFIG.came_port}")

    # Initialize storage
    storage = await get_storage()
    LOGGER.info("Storage initialized")

    # Create proxy handler and app
    proxy_handler = ProxyHandler()
    proxy_app = await create_proxy_app(proxy_handler)

    # Create dashboard and app
    dashboard = DashboardBackend()
    dashboard_app = await create_dashboard_app(dashboard)

    # Store dashboard reference in proxy for broadcasting
    proxy_app["dashboard"] = dashboard

    # Create runners
    proxy_runner = web.AppRunner(proxy_app)
    dashboard_runner = web.AppRunner(dashboard_app)

    try:
        # Setup and start proxy server
        await proxy_runner.setup()
        proxy_site = web.TCPSite(proxy_runner, "0.0.0.0", CONFIG.proxy_port)
        await proxy_site.start()
        LOGGER.info(f"Proxy server started on port {CONFIG.proxy_port}")

        # Setup and start dashboard server
        await dashboard_runner.setup()
        dashboard_site = web.TCPSite(dashboard_runner, "0.0.0.0", CONFIG.dashboard_port)
        await dashboard_site.start()
        LOGGER.info(f"Dashboard server started on port {CONFIG.dashboard_port}")

        # Keep running until interrupted
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        LOGGER.info("Received interrupt signal")
    except Exception as e:
        LOGGER.error(f"Error running servers: {e}", exc_info=True)
    finally:
        # Graceful shutdown
        LOGGER.info("Shutting down servers...")
        await proxy_runner.cleanup()
        await dashboard_runner.cleanup()
        await storage.close()
        LOGGER.info("Shutdown complete")


async def main() -> None:
    """Main async entry point."""
    try:
        await run_servers()
    except Exception as e:
        LOGGER.error(f"Fatal error: {e}", exc_info=True)
        raise


def run() -> None:
    """Synchronous entry point for CLI."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        LOGGER.error(f"Application error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run()
