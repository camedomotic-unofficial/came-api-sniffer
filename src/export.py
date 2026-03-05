"""Export module for CAME API Sniffer.

Implements export functionality to TXT format with proper formatting.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import CONFIG, LOGGER
from .storage import get_storage


class Exporter:
    """Export exchanges to TXT format."""

    def __init__(self):
        """Initialize exporter."""
        self.exports_dir = Path(CONFIG.data_dir) / "exports"
        self.exports_dir.mkdir(exist_ok=True)

    def _format_exchange(self, exchange: dict[str, Any]) -> str:
        """Format single exchange for export.

        Args:
            exchange: Exchange data dictionary.

        Returns:
            Formatted string.
        """
        separator = "=" * 70
        sep_section = "-" * 70

        lines = [separator]
        lines.append(f"EXCHANGE: {exchange['exchange_id']}")
        lines.append(f"SESSION:  {exchange.get('session_id', 'N/A')}")
        lines.append(f"METHOD:   {exchange.get('app_method', 'N/A')}")

        timestamp_start = exchange.get("timestamp_start", "N/A")
        timestamp_end = exchange.get("timestamp_end", "N/A")
        duration_ms = exchange.get("duration_ms", "N/A")
        lines.append(f"TIME:     {timestamp_start} → {timestamp_end} ({duration_ms}ms)")
        lines.append(separator)
        lines.append("")

        # REQUEST section — full HTTP format
        lines.append(sep_section)
        lines.append("REQUEST")
        lines.append(sep_section)

        method = exchange.get("method", "UNKNOWN")
        path = exchange.get("path", "/")
        query_string = exchange.get("query_string", "")
        url = f"{path}{'?' + query_string if query_string else ''}"
        lines.append(f"{method} {url} HTTP/1.1")

        # Headers
        request_headers = exchange.get("request_headers", {})
        if isinstance(request_headers, str):
            try:
                request_headers = json.loads(request_headers)
            except json.JSONDecodeError:
                request_headers = {}
        for key, value in request_headers.items():
            lines.append(f"{key}: {value}")

        lines.append("")  # blank line between headers and body

        # Raw body
        request_body = exchange.get("request_body")
        if request_body:
            lines.append(str(request_body))
        lines.append("")

        # RESPONSE section — full HTTP format
        lines.append(sep_section)
        lines.append("RESPONSE")
        lines.append(sep_section)

        status_code = exchange.get("status_code", "N/A")
        lines.append(f"HTTP/1.1 {status_code}")

        # Headers
        response_headers = exchange.get("response_headers", {})
        if isinstance(response_headers, str):
            try:
                response_headers = json.loads(response_headers)
            except json.JSONDecodeError:
                response_headers = {}
        for key, value in response_headers.items():
            lines.append(f"{key}: {value}")

        lines.append("")  # blank line between headers and body

        # Raw body
        response_body = exchange.get("response_body")
        if response_body:
            if isinstance(response_body, dict):
                lines.append(json.dumps(response_body))
            else:
                lines.append(str(response_body))
        lines.append("")

        lines.append(separator)
        lines.append("")

        return "\n".join(lines)

    async def export_all(self) -> Path:
        """Export all exchanges.

        Returns:
            Path to exported file.
        """
        try:
            storage = await get_storage()
            exchange_summaries, _ = await storage.query_exchanges(page=1, page_size=10000)

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"export_all_{timestamp}.txt"
            filepath = self.exports_dir / filename

            content = ""
            for summary in reversed(exchange_summaries):
                full = await storage.get_exchange(summary["exchange_id"])
                if full:
                    content += self._format_exchange(full)

            with open(filepath, "w") as f:
                f.write(content)

            LOGGER.info(f"Exported {len(exchange_summaries)} exchanges to {filename}")
            return filepath

        except Exception as e:
            LOGGER.error(f"Error exporting: {e}")
            raise

    async def export_session(self, session_id: str, exclude_method: Optional[str] = None) -> Path:
        """Export exchanges for specific session.

        Args:
            session_id: Session ID to export.
            exclude_method: App method to exclude from export (e.g. 'status_update_req').

        Returns:
            Path to exported file.
        """
        try:
            storage = await get_storage()
            exchange_summaries, _ = await storage.query_exchanges(
                page=1, page_size=10000, session_id=session_id
            )

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"export_session_{session_id}_{timestamp}.txt"
            filepath = self.exports_dir / filename

            content = ""
            for summary in reversed(exchange_summaries):
                if exclude_method and summary.get("app_method") == exclude_method:
                    continue
                full = await storage.get_exchange(summary["exchange_id"])
                if full:
                    content += self._format_exchange(full)

            with open(filepath, "w") as f:
                f.write(content)

            LOGGER.info(
                f"Exported {len(exchange_summaries)} exchanges for session {session_id} "
                f"to {filename}"
            )
            return filepath

        except Exception as e:
            LOGGER.error(f"Error exporting session: {e}")
            raise

    async def export_range(
        self, from_ts: str, to_ts: str
    ) -> Path:
        """Export exchanges in time range.

        Args:
            from_ts: Start timestamp (ISO 8601).
            to_ts: End timestamp (ISO 8601).

        Returns:
            Path to exported file.
        """
        try:
            storage = await get_storage()
            exchange_summaries, _ = await storage.query_exchanges(
                page=1, page_size=10000, from_ts=from_ts, to_ts=to_ts
            )

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"export_range_{from_ts}_{to_ts}_{timestamp}.txt"
            filepath = self.exports_dir / filename

            content = ""
            for summary in reversed(exchange_summaries):
                full = await storage.get_exchange(summary["exchange_id"])
                if full:
                    content += self._format_exchange(full)

            with open(filepath, "w") as f:
                f.write(content)

            LOGGER.info(
                f"Exported {len(exchange_summaries)} exchanges for range "
                f"{from_ts} to {to_ts} to {filename}"
            )
            return filepath

        except Exception as e:
            LOGGER.error(f"Error exporting range: {e}")
            raise


# Global exporter instance
exporter: Optional[Exporter] = None


async def get_exporter() -> Exporter:
    """Get or create global exporter instance.

    Returns:
        Exporter: Global instance.
    """
    global exporter
    if exporter is None:
        exporter = Exporter()
    return exporter
