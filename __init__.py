"""
micro_mcp
~~~~~~~~~

A pure-Python MCP (Model Context Protocol) server framework — **zero
external dependencies**.

Provides a FastMCP-style decorator API for building MCP servers::

    from micro_mcp import MCPServer

    mcp = MCPServer("demo")

    @mcp.tool()
    def add(a: int, b: int) -> int:
        \"\"\"Add two numbers.\"\"\"
        return a + b

    mcp.run()   # STDIO by default

Public API
----------
- ``MCPServer``   — the main server class.
- ``MCPContext``   — request-scoped context for tool handlers.
- ``TextContent``  — text content block.
- ``ImageContent`` — image content block.
"""

__version__ = "0.1.0"

from .server import MCPServer
from .context import MCPContext
from .mcp_types import TextContent, ImageContent, EmbeddedResource

__all__ = [
    "MCPServer",
    "MCPContext",
    "TextContent",
    "ImageContent",
    "EmbeddedResource",
]
