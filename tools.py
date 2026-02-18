"""
micro_mcp.tools
~~~~~~~~~~~~~~~

Tool registry — register Python functions as MCP tools, generate schemas,
and execute tool calls.

No external dependencies — pure Python stdlib only.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .context import MCPContext
from .errors import InvalidParamsError, MethodNotFoundError
from .mcp_types import TextContent, generate_schema, _get_description


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ToolInfo:
    """Metadata for a registered tool.

    Attributes
    ----------
    name : str
        Unique tool name (defaults to the function name).
    description : str
        Human-readable description (from the docstring or explicit).
    input_schema : dict
        JSON Schema describing the tool's expected parameters.
    handler : Callable
        The Python function that implements this tool.
    """

    name: str
    description: str
    input_schema: dict
    handler: Callable


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Registry that stores and manages MCP tools.

    Usage::

        registry = ToolRegistry()

        def greet(name: str) -> str:
            \"\"\"Say hello.\"\"\"
            return f"Hello, {name}!"

        registry.register(greet)
        result = registry.execute("greet", {"name": "World"})
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolInfo] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        func: Callable,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> ToolInfo:
        """Register a callable as an MCP tool.

        Parameters
        ----------
        func:
            The function to register.
        name:
            Override for the tool name (defaults to ``func.__name__``).
        description:
            Override for the description (defaults to docstring).

        Returns
        -------
        ToolInfo
            The created tool metadata.

        Raises
        ------
        ValueError
            If a tool with the same name is already registered.
        """
        tool_name = name or func.__name__
        if tool_name in self._tools:
            raise ValueError(f"Tool already registered: {tool_name!r}")

        tool_desc = description or _get_description(func)
        schema = generate_schema(func)

        info = ToolInfo(
            name=tool_name,
            description=tool_desc,
            input_schema=schema,
            handler=func,
        )
        self._tools[tool_name] = info
        return info

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_tools(self) -> List[dict]:
        """Return the list of tools in MCP ``tools/list`` response format.

        Returns
        -------
        list[dict]
            Each dict has ``name``, ``description``, and ``inputSchema``.
        """
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    def get(self, name: str) -> ToolInfo:
        """Look up a tool by name.

        Raises
        ------
        MethodNotFoundError
            If no tool with that name exists.
        """
        if name not in self._tools:
            raise MethodNotFoundError(f"Tool not found: {name!r}")
        return self._tools[name]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        ctx: Optional[MCPContext] = None,
    ) -> dict:
        """Execute a tool synchronously and return a ``CallToolResult``.

        Parameters
        ----------
        name:
            Tool name.
        arguments:
            Named arguments to pass to the handler.
        ctx:
            Optional request context (injected as ``ctx`` if the handler
            accepts it).

        Returns
        -------
        dict
            MCP ``CallToolResult`` with ``content`` list and ``isError`` flag.
        """
        tool = self.get(name)
        args = arguments or {}

        try:
            result = self._invoke(tool.handler, args, ctx)
            return self._wrap_result(result, is_error=False)
        except Exception as exc:
            return self._wrap_result(str(exc), is_error=True)

    async def execute_async(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        ctx: Optional[MCPContext] = None,
    ) -> dict:
        """Execute a tool (sync or async handler) and return a ``CallToolResult``.

        Parameters
        ----------
        name:
            Tool name.
        arguments:
            Named arguments to pass to the handler.
        ctx:
            Optional request context.

        Returns
        -------
        dict
            MCP ``CallToolResult``.
        """
        tool = self.get(name)
        args = arguments or {}

        try:
            result = self._invoke(tool.handler, args, ctx)
            # If the handler is async, await the coroutine
            if asyncio.iscoroutine(result):
                result = await result
            return self._wrap_result(result, is_error=False)
        except Exception as exc:
            return self._wrap_result(str(exc), is_error=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _invoke(handler: Callable, args: Dict[str, Any], ctx: Optional[MCPContext]):
        """Call *handler* with *args*, injecting *ctx* if requested."""
        sig = inspect.signature(handler)
        # If the handler accepts a 'ctx' parameter, inject the context
        if "ctx" in sig.parameters and ctx is not None:
            args = {**args, "ctx": ctx}
        return handler(**args)

    @staticmethod
    def _wrap_result(result: Any, is_error: bool = False) -> dict:
        """Wrap a raw return value into an MCP ``CallToolResult``.

        The result is normalized into a list of content blocks.
        """
        if isinstance(result, dict) and "content" in result:
            # Already structured
            result.setdefault("isError", is_error)
            return result

        # Convert to content blocks
        if isinstance(result, list):
            content = []
            for item in result:
                if isinstance(item, dict) and "type" in item:
                    content.append(item)
                elif hasattr(item, "to_dict"):
                    content.append(item.to_dict())
                else:
                    content.append(TextContent(text=str(item)).to_dict())
        elif hasattr(result, "to_dict"):
            content = [result.to_dict()]
        else:
            content = [TextContent(text=str(result)).to_dict()]

        return {"content": content, "isError": is_error}
