"""
micro_mcp.transport.sse
~~~~~~~~~~~~~~~~~~~~~~~

SSE (Server-Sent Events) transport — runs an HTTP server using Python's
built-in ``http.server`` module.

Endpoints
---------
- ``GET  /sse``       →  Opens an SSE stream (server → client).
- ``POST /messages``  →  Receives JSON-RPC messages (client → server).

Each client session is assigned a unique ID.  The ``POST /messages``
endpoint processes the request, and the response is sent back as an SSE
event on the corresponding stream.

No external dependencies — pure Python stdlib only.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from ..server import MCPServer


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

# Maps session_id → queue of SSE events to send to the client.
_sessions: Dict[str, queue.Queue] = {}


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class _SSEHandler(BaseHTTPRequestHandler):
    """HTTP handler for both SSE streaming and JSON-RPC message ingestion."""

    # Reference to the MCPServer — set on the *class* before use.
    mcp_server: "MCPServer"

    # asyncio event loop running in a background thread.
    _loop: asyncio.AbstractEventLoop

    # Suppress default stderr access logging
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        from ..logger import get_logger
        get_logger("micro_mcp.sse").debug(format % args)

    # ------------------------------------------------------------------
    # GET /sse — open an SSE stream
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/sse":
            self.send_error(404, "Not Found")
            return

        session_id = uuid.uuid4().hex
        q: queue.Queue = queue.Queue()
        _sessions[session_id] = q

        from ..logger import get_logger
        log = get_logger("micro_mcp.sse")
        log.info(f"SSE: new session {session_id}")

        # Send headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Send the endpoint event so the client knows where to POST
        self._send_sse_event(
            "endpoint",
            f"/messages?session_id={session_id}",
        )

        try:
            while True:
                # Block until a response arrives (or timeout for keep-alive)
                try:
                    event_data = q.get(timeout=30)
                except queue.Empty:
                    # Send a keep-alive comment
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    continue

                if event_data is None:
                    # Sentinel — close the stream
                    break

                self._send_sse_event("message", event_data)

        except (BrokenPipeError, ConnectionResetError):
            log.info(f"SSE: client disconnected (session {session_id})")
        finally:
            _sessions.pop(session_id, None)

    # ------------------------------------------------------------------
    # POST /messages — receive a JSON-RPC message
    # ------------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/messages"):
            self.send_error(404, "Not Found")
            return

        # Extract session_id from query string
        session_id = self._query_param("session_id")
        if not session_id or session_id not in _sessions:
            self.send_error(400, "Invalid or missing session_id")
            return

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        from ..logger import get_logger
        log = get_logger("micro_mcp.sse")
        log.debug(f"SSE POST ← {body}")

        # Dispatch through the server (run the async handler on our loop)
        future = asyncio.run_coroutine_threadsafe(
            self.mcp_server.handle_message(body),
            self._loop,
        )
        response = future.result(timeout=30)

        if response is not None:
            # Push the response onto the SSE queue for this session
            _sessions[session_id].put(response)

        # Acknowledge the POST
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b'{"status":"accepted"}')

    # ------------------------------------------------------------------
    # OPTIONS (CORS preflight)
    # ------------------------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _send_sse_event(self, event: str, data: str) -> None:
        """Write a single SSE event frame to the response stream."""
        payload = f"event: {event}\ndata: {data}\n\n"
        self.wfile.write(payload.encode("utf-8"))
        self.wfile.flush()

    def _query_param(self, key: str) -> Optional[str]:
        """Extract a query parameter from ``self.path``."""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        values = params.get(key)
        return values[0] if values else None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_sse(
    server: "MCPServer",
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Start the MCP server with SSE transport.

    This spins up an HTTP server on the given *host*:*port*.

    Parameters
    ----------
    server:
        The ``MCPServer`` instance.
    host:
        Bind address (default ``"127.0.0.1"``).
    port:
        Bind port (default ``8000``).
    """
    from ..logger import get_logger
    log = get_logger("micro_mcp.sse")

    # Create a background asyncio loop for running the server's async handlers
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()

    # Run startup hooks
    asyncio.run_coroutine_threadsafe(server._run_startup(), loop).result()

    # Configure the handler class
    _SSEHandler.mcp_server = server
    _SSEHandler._loop = loop

    httpd = HTTPServer((host, port), _SSEHandler)
    log.info(f"SSE transport listening on http://{host}:{port}")
    log.info(f"  SSE endpoint:     GET  http://{host}:{port}/sse")
    log.info(f"  Message endpoint: POST http://{host}:{port}/messages")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("SSE: shutting down")
    finally:
        asyncio.run_coroutine_threadsafe(server._run_shutdown(), loop).result()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=5)
        httpd.server_close()
        log.info("SSE: server stopped")
