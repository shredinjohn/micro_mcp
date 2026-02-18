"""
micro_mcp.server
~~~~~~~~~~~~~~~~

The core ``MCPServer`` class — the main entry point for building MCP servers.

Provides a FastMCP-style **decorator API** for registering tools, resources,
and prompts, plus built-in JSON-RPC method dispatching and transport
integration.

Usage::

    from micro_mcp import MCPServer

    mcp = MCPServer("MyService")

    @mcp.tool()
    def greet(name: str) -> str:
        \"\"\"Say hello.\"\"\"
        return f"Hello, {name}!"

    @mcp.resource("data://info")
    def info() -> str:
        \"\"\"Static info resource.\"\"\"
        return "Some info"

    @mcp.prompt()
    def ask(question: str) -> list:
        \"\"\"Ask a question.\"\"\"
        return [{"role": "user", "content": question}]

    mcp.run()            # STDIO transport (default)
    mcp.run("sse")       # SSE / HTTP transport

No external dependencies — pure Python stdlib only.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Callable, Dict, List, Optional, Union

from .context import MCPContext
from .errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    InternalError,
    InvalidParamsError,
    MCPError,
    MethodNotFoundError,
)
from .jsonrpc import (
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    make_error_response,
    make_error_response_from_exc,
    make_response,
    parse_message,
    serialize,
)
from .logger import get_logger
from .prompts import PromptRegistry
from .resources import ResourceRegistry
from .tools import ToolRegistry

# MCP protocol version this server advertises.
MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPServer:
    """A complete MCP server with decorator-based registration.

    Parameters
    ----------
    name : str
        Human-readable server name.
    version : str
        Server version string.
    """

    def __init__(self, name: str = "micro_mcp", version: str = "1.0.0") -> None:
        self.name = name
        self.version = version

        # Registries
        self._tools = ToolRegistry()
        self._resources = ResourceRegistry()
        self._prompts = PromptRegistry()

        # Lifecycle hooks
        self._startup_hooks: List[Callable] = []
        self._shutdown_hooks: List[Callable] = []

        # Logger (writes to stderr)
        self._log = get_logger(f"micro_mcp.{name}")

        # Whether the server has completed the `initialize` handshake
        self._initialized = False

    # ==================================================================
    # Decorator API
    # ==================================================================

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Callable:
        """Decorator to register a function as an MCP tool.

        Can be used with or without arguments::

            @mcp.tool()
            def my_tool(x: int) -> str: ...

            @mcp.tool(name="custom_name")
            def another(x: int) -> str: ...

        Parameters
        ----------
        name:
            Override tool name (default: function name).
        description:
            Override tool description (default: docstring).
        """
        def decorator(func: Callable) -> Callable:
            self._tools.register(func, name=name, description=description)
            return func
        return decorator

    def resource(
        self,
        uri: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: str = "text/plain",
    ) -> Callable:
        """Decorator to register a function as an MCP resource.

        Usage::

            @mcp.resource("data://config")
            def config() -> str: ...

            @mcp.resource("users://{user_id}/profile")
            def profile(user_id: str) -> str: ...

        Parameters
        ----------
        uri:
            Resource URI or URI template.
        name:
            Override resource name.
        description:
            Override resource description.
        mime_type:
            Content MIME type (default ``"text/plain"``).
        """
        def decorator(func: Callable) -> Callable:
            self._resources.register(
                uri, func,
                name=name, description=description, mime_type=mime_type,
            )
            return func
        return decorator

    def prompt(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Callable:
        """Decorator to register a function as an MCP prompt.

        Usage::

            @mcp.prompt()
            def summarize(text: str) -> list: ...

        Parameters
        ----------
        name:
            Override prompt name.
        description:
            Override prompt description.
        """
        def decorator(func: Callable) -> Callable:
            self._prompts.register(func, name=name, description=description)
            return func
        return decorator

    # ==================================================================
    # Lifecycle hooks
    # ==================================================================

    def on_startup(self, func: Callable) -> Callable:
        """Register a function to run when the server starts.

        Usage::

            @mcp.on_startup
            def setup():
                print("Server starting…", file=sys.stderr)
        """
        self._startup_hooks.append(func)
        return func

    def on_shutdown(self, func: Callable) -> Callable:
        """Register a function to run when the server shuts down.

        Usage::

            @mcp.on_shutdown
            def teardown():
                print("Server stopping…", file=sys.stderr)
        """
        self._shutdown_hooks.append(func)
        return func

    # ==================================================================
    # JSON-RPC Method Dispatch
    # ==================================================================

    async def handle_message(
        self, raw: str
    ) -> Optional[str]:
        """Parse and dispatch a raw JSON-RPC message string.

        Parameters
        ----------
        raw : str
            Incoming JSON string.

        Returns
        -------
        str | None
            Serialized JSON-RPC response, or ``None`` for notifications.
        """
        try:
            msg = parse_message(raw)
        except MCPError as exc:
            resp = make_error_response_from_exc(None, exc)
            return serialize(resp)

        # Batch requests
        if isinstance(msg, list):
            responses = []
            for m in msg:
                r = await self._dispatch(m)
                if r is not None:
                    responses.append(r)
            if not responses:
                return None
            return json.dumps(
                [json.loads(serialize(r)) for r in responses],
                separators=(",", ":"),
            )

        resp = await self._dispatch(msg)
        if resp is None:
            return None
        return serialize(resp)

    async def _dispatch(
        self,
        msg: Union[JSONRPCRequest, JSONRPCNotification],
    ) -> Optional[JSONRPCResponse]:
        """Route a parsed message to the appropriate handler.

        Returns ``None`` for notifications (no response expected).
        """
        method = msg.method
        params = msg.params or {}
        is_notification = isinstance(msg, JSONRPCNotification)
        request_id = getattr(msg, "id", None)

        self._log.debug(f"Dispatching method={method!r}")

        # Map method names to handlers
        handler_map: Dict[str, Callable] = {
            "initialize": self._handle_initialize,
            "initialized": self._handle_initialized,
            "ping": self._handle_ping,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "resources/templates/list": self._handle_resources_templates_list,
            "prompts/list": self._handle_prompts_list,
            "prompts/get": self._handle_prompts_get,
        }

        handler = handler_map.get(method)
        if handler is None:
            if is_notification:
                return None
            return make_error_response(
                request_id, METHOD_NOT_FOUND,
                f"Method not found: {method!r}",
            )

        try:
            result = await handler(params)  # type: ignore[arg-type]
        except MCPError as exc:
            if is_notification:
                return None
            return make_error_response_from_exc(request_id, exc)
        except Exception as exc:
            self._log.error(f"Unhandled error in {method}: {exc}")
            if is_notification:
                return None
            return make_error_response(
                request_id, INTERNAL_ERROR, f"Internal error: {exc}",
            )

        if is_notification:
            return None
        return make_response(request_id, result)

    # ==================================================================
    # MCP Protocol Handlers
    # ==================================================================

    async def _handle_initialize(self, params: dict) -> dict:
        """Handle the ``initialize`` handshake.

        Returns server info and capabilities.
        """
        self._log.info(
            f"Initialize request from client: "
            f"{params.get('clientInfo', {}).get('name', 'unknown')}"
        )

        capabilities: Dict[str, Any] = {}

        # Advertise tool support if any tools are registered
        if self._tools.list_tools():
            capabilities["tools"] = {"listChanged": False}

        # Advertise resource support if any resources are registered
        if self._resources.list_resources() or self._resources.list_templates():
            capabilities["resources"] = {"subscribe": False, "listChanged": False}

        # Advertise prompt support if any prompts are registered
        if self._prompts.list_prompts():
            capabilities["prompts"] = {"listChanged": False}

        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": capabilities,
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
        }

    async def _handle_initialized(self, params: dict) -> None:
        """Handle the ``initialized`` notification from the client."""
        self._initialized = True
        self._log.info("Client initialized successfully")

    async def _handle_ping(self, params: dict) -> dict:
        """Handle ``ping`` — returns an empty object."""
        return {}

    async def _handle_tools_list(self, params: dict) -> dict:
        """Handle ``tools/list`` — return all registered tools."""
        return {"tools": self._tools.list_tools()}

    async def _handle_tools_call(self, params: dict) -> dict:
        """Handle ``tools/call`` — execute a tool by name."""
        tool_name = params.get("name")
        if not tool_name:
            raise InvalidParamsError("Missing 'name' parameter")

        arguments = params.get("arguments", {})

        # Create a per-request context
        ctx = MCPContext(
            request_id=None,
            server_name=self.name,
        )

        result = await self._tools.execute_async(tool_name, arguments, ctx)
        return result

    async def _handle_resources_list(self, params: dict) -> dict:
        """Handle ``resources/list``."""
        return {"resources": self._resources.list_resources()}

    async def _handle_resources_read(self, params: dict) -> dict:
        """Handle ``resources/read``."""
        uri = params.get("uri")
        if not uri:
            raise InvalidParamsError("Missing 'uri' parameter")
        return self._resources.read(uri)

    async def _handle_resources_templates_list(self, params: dict) -> dict:
        """Handle ``resources/templates/list``."""
        return {"resourceTemplates": self._resources.list_templates()}

    async def _handle_prompts_list(self, params: dict) -> dict:
        """Handle ``prompts/list``."""
        return {"prompts": self._prompts.list_prompts()}

    async def _handle_prompts_get(self, params: dict) -> dict:
        """Handle ``prompts/get``."""
        prompt_name = params.get("name")
        if not prompt_name:
            raise InvalidParamsError("Missing 'name' parameter")
        arguments = params.get("arguments", {})
        return self._prompts.get(prompt_name, arguments)

    # ==================================================================
    # Server Lifecycle
    # ==================================================================

    async def _run_startup(self) -> None:
        """Execute all registered startup hooks."""
        for hook in self._startup_hooks:
            if asyncio.iscoroutinefunction(hook):
                await hook()
            else:
                hook()

    async def _run_shutdown(self) -> None:
        """Execute all registered shutdown hooks."""
        for hook in self._shutdown_hooks:
            if asyncio.iscoroutinefunction(hook):
                await hook()
            else:
                hook()

    # ==================================================================
    # Transport Entry Points
    # ==================================================================

    def run(
        self,
        transport: str = "stdio",
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
    ) -> None:
        """Start the server with the specified transport.

        Parameters
        ----------
        transport : str
            ``"stdio"`` (default) or ``"sse"``.
        host : str
            Bind address for SSE transport (default ``"127.0.0.1"``).
        port : int
            Bind port for SSE transport (default ``8000``).
        """
        transport = transport.lower().strip()
        if transport == "stdio":
            from .transport.stdio import run_stdio
            asyncio.run(run_stdio(self))
        elif transport == "sse":
            from .transport.sse import run_sse
            run_sse(self, host=host, port=port)
        else:
            raise ValueError(f"Unknown transport: {transport!r}  (use 'stdio' or 'sse')")
