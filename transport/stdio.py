"""
micro_mcp.transport.stdio
~~~~~~~~~~~~~~~~~~~~~~~~~

STDIO transport — reads newline-delimited JSON-RPC messages from **stdin**
and writes JSON-RPC responses to **stdout**.

This is the default MCP transport: an MCP client launches the server as a
subprocess and communicates via standard I/O streams.

Uses a threading-based approach for cross-platform compatibility (Windows
does not support ``asyncio.connect_read_pipe`` on regular file handles).

No external dependencies — pure Python stdlib only.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..server import MCPServer


async def run_stdio(server: "MCPServer") -> None:
    """Run the MCP server over STDIO.

    Reads one JSON-RPC message per line from ``stdin``, dispatches it
    through the server, and writes the response to ``stdout``.

    Parameters
    ----------
    server:
        The ``MCPServer`` instance to drive.
    """
    from ..logger import get_logger
    log = get_logger("micro_mcp.stdio")

    # Run startup hooks
    await server._run_startup()
    log.info(f"Server '{server.name}' running on STDIO transport")

    loop = asyncio.get_running_loop()

    # Use a thread to read stdin line-by-line (Windows-compatible).
    # Lines are pushed into an asyncio.Queue for the main loop to process.
    line_queue: asyncio.Queue = asyncio.Queue()

    def _reader_thread():
        """Background thread: reads lines from stdin and puts them in the queue."""
        try:
            for line in sys.stdin:
                # Schedule the put on the event loop so it's thread-safe
                asyncio.run_coroutine_threadsafe(line_queue.put(line), loop)
        except (EOFError, ValueError):
            pass
        finally:
            # Signal EOF with None sentinel
            asyncio.run_coroutine_threadsafe(line_queue.put(None), loop)

    reader = threading.Thread(target=_reader_thread, daemon=True)
    reader.start()

    try:
        while True:
            line = await line_queue.get()
            if line is None:
                # EOF — client disconnected
                log.info("STDIO: EOF received, shutting down")
                break

            raw = line.strip()
            if not raw:
                continue

            log.debug(f"STDIO ← {raw}")

            response = await server.handle_message(raw)

            if response is not None:
                log.debug(f"STDIO → {response}")
                # Write the response followed by a newline
                sys.stdout.write(response + "\n")
                sys.stdout.flush()

    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("STDIO: interrupted")
    finally:
        await server._run_shutdown()
        log.info("STDIO: server stopped")
