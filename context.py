"""
micro_mcp.context
~~~~~~~~~~~~~~~~~

Request-scoped context object that is available inside tool handlers.

Provides helpers for logging, progress reporting, and accessing request
metadata.  An ``MCPContext`` is automatically created for each incoming
``tools/call`` request and can be accepted by tool handlers as a parameter
named ``ctx``.

No external dependencies — pure Python stdlib only.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from .logger import get_logger


class MCPContext:
    """Per-request context passed to tool handlers.

    Attributes
    ----------
    request_id:
        The JSON-RPC request ``id`` for this invocation.
    server_name:
        Name of the MCP server handling the request.
    _progress_callback:
        Optional callback for emitting progress notifications.
    """

    def __init__(
        self,
        request_id: Any = None,
        server_name: str = "micro_mcp",
        progress_callback: Optional[Callable] = None,
    ):
        self.request_id = request_id
        self.server_name = server_name
        self._progress_callback = progress_callback
        self._logger = get_logger(f"micro_mcp.ctx.{server_name}")

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def info(self, msg: str) -> None:
        """Log an informational message."""
        self._logger.info(msg)

    def warning(self, msg: str) -> None:
        """Log a warning message."""
        self._logger.warning(msg)

    def error(self, msg: str) -> None:
        """Log an error message."""
        self._logger.error(msg)

    def debug(self, msg: str) -> None:
        """Log a debug message."""
        self._logger.debug(msg)

    # ------------------------------------------------------------------
    # Progress reporting
    # ------------------------------------------------------------------

    def report_progress(self, progress: float, total: float = 1.0) -> None:
        """Report progress to the client (if a callback is registered).

        Parameters
        ----------
        progress:
            Current progress value.
        total:
            Total expected value (default 1.0).
        """
        if self._progress_callback is not None:
            self._progress_callback(self.request_id, progress, total)
