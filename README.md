<p align="center">
  <h1 align="center">⚡ micro_mcp</h1>
  <p align="center">A lightweight, zero-dependency MCP (Model Context Protocol) server framework for Python</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/dependencies-zero-brightgreen?style=flat-square" alt="Zero Dependencies">
  <img src="https://img.shields.io/badge/tests-79%20passing-success?style=flat-square" alt="Tests Passing">
  <img src="https://img.shields.io/badge/license-MIT-orange?style=flat-square" alt="MIT License">
</p>

---

**micro_mcp** is a complete MCP server framework built from scratch using **only Python's standard library**. It provides a FastMCP-style decorator API that lets you build MCP-compliant servers in minutes — no pip installs, no dependency conflicts, just pure Python.

```python
from micro_mcp import MCPServer

mcp = MCPServer("MyServer")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

mcp.run()
```

That's it. Your AI assistant can now call `add(3, 5)`.

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Core Concepts](#core-concepts)
  - [Tools](#tools)
  - [Resources](#resources)
  - [Prompts](#prompts)
  - [Context](#context)
  - [Lifecycle Hooks](#lifecycle-hooks)
- [Transport Layers](#transport-layers)
  - [STDIO Transport](#stdio-transport)
  - [SSE Transport](#sse-transport)
- [Content Types](#content-types)
- [Schema Generation](#automatic-schema-generation)
- [Error Handling](#error-handling)
- [VS Code Integration](#vs-code-integration)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [API Reference](#api-reference)

---

## Features

| Feature | Description |
|---|---|
| 🚀 **Zero Dependencies** | Built entirely with Python's standard library — no `pip install` needed |
| 🎨 **Decorator API** | FastMCP-style `@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()` decorators |
| 📐 **Auto Schema Generation** | Generates JSON Schema from Python type hints — no Pydantic required |
| 🔌 **Two Transports** | STDIO (subprocess) and SSE (HTTP) out of the box |
| ⚡ **Async Support** | Handles both `sync` and `async` tool handlers seamlessly |
| 📡 **JSON-RPC 2.0** | Full protocol implementation including batch requests |
| 🛡️ **Error Handling** | Standard MCP/JSON-RPC error codes with typed exceptions |
| 📋 **Context Injection** | Per-request `MCPContext` with logging and progress reporting |
| 🔄 **Lifecycle Hooks** | `@mcp.on_startup` and `@mcp.on_shutdown` decorators |
| 🧪 **Fully Tested** | 79 tests covering every module |
| 🖥️ **Cross-Platform** | Works on Windows, macOS, and Linux |

---

## Quick Start

### 1. Create a server

```python
# my_server.py
from micro_mcp import MCPServer

mcp = MCPServer("DemoServer", version="1.0.0")

@mcp.tool()
def greet(name: str, greeting: str = "Hello") -> str:
    """Greet someone by name."""
    return f"{greeting}, {name}! 👋"

@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a math expression safely."""
    allowed = set("0123456789+-*/.(). ")
    if all(c in allowed for c in expression):
        return str(eval(expression))
    return "Error: Invalid expression"

mcp.run()  # Starts STDIO transport
```

### 2. Run it

```bash
python my_server.py
```

### 3. Connect from VS Code

Create `.vscode/mcp.json` in your workspace:

```json
{
    "servers": {
        "demo-server": {
            "type": "stdio",
            "command": "python",
            "args": ["path/to/my_server.py"]
        }
    }
}
```

Your AI assistant (GitHub Copilot, etc.) will now see and use your tools.

---

## Installation

No installation needed! Just copy the `micro_mcp/` directory into your project:

```
your-project/
├── micro_mcp/          ← Copy this folder
│   ├── __init__.py
│   ├── server.py
│   ├── ...
├── my_server.py        ← Your server
```

Then import:

```python
from micro_mcp import MCPServer
```

**Requirements:** Python 3.10+ (uses `from __future__ import annotations` and `typing` features).

---

## Core Concepts

### Tools

Tools are functions that an AI model can **call** to perform actions. They are the bread and butter of MCP.

#### Basic Tool

```python
@mcp.tool()
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"Weather in {city}: 22°C, Sunny"
```

The decorator auto-generates:
- **Name** → from the function name (`get_weather`)
- **Description** → from the docstring
- **Input Schema** → from type hints (`city: str` → `{"type": "string"}`)

#### Custom Name & Description

```python
@mcp.tool(name="fetch_weather", description="Fetches real-time weather data")
def get_weather(city: str) -> str:
    return f"Weather in {city}: 22°C"
```

#### Async Tools

```python
@mcp.tool()
async def slow_operation(query: str) -> str:
    """An async tool — awaited automatically."""
    await asyncio.sleep(1)
    return f"Result for: {query}"
```

#### Complex Type Hints

The schema generator handles complex Python types:

```python
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class Location:
    lat: float
    lon: float

@mcp.tool()
def search(
    query: str,                          # → {"type": "string"}
    limit: int = 10,                     # → {"type": "integer"}, optional
    tags: Optional[List[str]] = None,    # → {"type": "array", "items": {"type": "string"}}
) -> str:
    """Search with filters."""
    return "results..."
```

**Supported type mappings:**

| Python Type | JSON Schema |
|---|---|
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list` / `List[T]` | `{"type": "array", "items": ...}` |
| `dict` / `Dict[str, T]` | `{"type": "object", "additionalProperties": ...}` |
| `Optional[T]` | `{"anyOf": [T_schema, {"type": "null"}]}` |
| `Union[A, B]` | `{"anyOf": [A_schema, B_schema]}` |
| `@dataclass` | `{"type": "object", "properties": ...}` (recursive) |
| `Any` / missing | `{}` (accepts anything) |

---

### Resources

Resources expose **data** that the AI can read. They use URI patterns.

#### Static Resource

```python
@mcp.resource("config://app/settings", mime_type="application/json")
def app_settings() -> str:
    """Returns the application configuration."""
    return '{"theme": "dark", "lang": "en"}'
```

#### Template Resource (Dynamic URIs)

```python
@mcp.resource("users://{user_id}/profile")
def user_profile(user_id: str) -> str:
    """Fetch a user's profile by ID."""
    return f'{{"id": "{user_id}", "name": "Alice"}}'
```

When the AI reads `users://42/profile`, micro_mcp extracts `user_id="42"` and calls your handler.

#### Binary Resources

Return `bytes` for binary data — it's automatically base64-encoded:

```python
@mcp.resource("images://logo.png", mime_type="image/png")
def logo() -> bytes:
    with open("logo.png", "rb") as f:
        return f.read()
```

#### Resource Parameters

| Parameter | Type | Description |
|---|---|---|
| `uri` | `str` | URI pattern — use `{param}` for template segments |
| `name` | `str` | Override resource name (default: function name) |
| `description` | `str` | Override description (default: docstring) |
| `mime_type` | `str` | Content type (default: `"text/plain"`) |

---

### Prompts

Prompts are **reusable templates** that guide how the AI should approach a task.

#### Single-Turn Prompt

```python
@mcp.prompt()
def summarize(text: str, style: str = "concise") -> str:
    """Summarize text in a given style."""
    return f"Please summarize the following text in a {style} style:\n\n{text}"
```

Return a `str` → it becomes a single **user** message.

#### Multi-Turn Prompt

Return a `list` of message dicts for complex conversations:

```python
@mcp.prompt()
def code_review(code: str, language: str = "python") -> list:
    """Review code for best practices."""
    return [
        {
            "role": "user",
            "content": f"Review this {language} code for best practices:\n\n```{language}\n{code}\n```"
        },
        {
            "role": "assistant",
            "content": "I'll review the code focusing on: readability, performance, security, and best practices."
        },
        {
            "role": "user",
            "content": "Please also suggest specific improvements with code examples."
        }
    ]
```

#### Prompt Arguments

Arguments are auto-introspected from the function signature:
- Parameters **without defaults** → `required: true`
- Parameters **with defaults** → `required: false`

---

### Context

Tool handlers can receive a **request-scoped context** by adding a `ctx` parameter:

```python
from micro_mcp import MCPContext

@mcp.tool()
def process_data(data: str, ctx: MCPContext = None) -> str:
    """A tool that uses context for logging and progress."""

    ctx.info("Starting data processing...")
    ctx.debug(f"Input size: {len(data)} chars")

    # Report progress (0.0 to 1.0)
    ctx.report_progress(0.0)
    result = data.upper()
    ctx.report_progress(0.5)
    result = result.strip()
    ctx.report_progress(1.0)

    ctx.info("Processing complete!")
    return result
```

**MCPContext API:**

| Method | Description |
|---|---|
| `ctx.info(msg)` | Log an info message (to stderr) |
| `ctx.warning(msg)` | Log a warning |
| `ctx.error(msg)` | Log an error |
| `ctx.debug(msg)` | Log a debug message |
| `ctx.report_progress(progress, total)` | Report progress to the client |
| `ctx.request_id` | The JSON-RPC request ID |
| `ctx.server_name` | Name of the server |

> **Note:** Context is automatically injected — if your function has a parameter named `ctx`, it receives the context. If not, nothing is injected. Both sync and async handlers support context.

---

### Lifecycle Hooks

Run setup/teardown code when the server starts and stops:

```python
@mcp.on_startup
def initialize():
    """Runs when the server starts (before handling requests)."""
    print("Loading database connections...", file=sys.stderr)

@mcp.on_shutdown
def cleanup():
    """Runs when the server shuts down."""
    print("Closing connections...", file=sys.stderr)
```

You can register **multiple hooks** — they run in registration order:

```python
@mcp.on_startup
def load_config():
    print("Loading config...", file=sys.stderr)

@mcp.on_startup
def connect_db():
    print("Connecting to database...", file=sys.stderr)
```

---

## Transport Layers

### STDIO Transport

The **default** transport. The MCP client launches your server as a subprocess and communicates via stdin/stdout.

```python
mcp.run()           # Default: STDIO
mcp.run("stdio")    # Explicit
```

**How it works:**
1. Client spawns `python my_server.py`
2. Sends JSON-RPC messages as newline-delimited JSON to stdin
3. Reads JSON-RPC responses from stdout
4. All logging goes to **stderr** (never pollutes the JSON stream)

**Uses a threading-based stdin reader** for cross-platform compatibility (Windows doesn't support `asyncio.connect_read_pipe` on regular file handles).

---

### SSE Transport

HTTP-based transport using Server-Sent Events. Useful for:
- Browser-based clients
- Testing with tools like `curl`
- Remote server deployments

```python
mcp.run("sse")  # Starts HTTP server on port 8000
```

**Endpoints:**

| Endpoint | Method | Description |
|---|---|---|
| `GET /sse` | GET | Stream — emits a `sessionId`, then JSON-RPC responses as SSE events |
| `POST /messages?session_id=<id>` | POST | Send a JSON-RPC request to the server |

**Configuration via environment:**

```bash
MCP_SSE_HOST=0.0.0.0 MCP_SSE_PORT=9000 python my_server.py --transport sse
```

**Example with curl:**

```bash
# Terminal 1: Connect to SSE stream
curl -N http://localhost:8000/sse

# Terminal 2: Send a request (use the session_id from Terminal 1)
curl -X POST "http://localhost:8000/messages?session_id=<ID>" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

---

## Content Types

Tools and resources can return rich content types:

### TextContent

```python
from micro_mcp import TextContent

@mcp.tool()
def analyze(text: str) -> TextContent:
    return TextContent(text=f"Analysis: {text}")
```

### ImageContent

```python
from micro_mcp import ImageContent
import base64

@mcp.tool()
def screenshot() -> ImageContent:
    with open("screenshot.png", "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return ImageContent(data=data, mime_type="image/png")
```

### EmbeddedResource

```python
from micro_mcp import EmbeddedResource

@mcp.tool()
def fetch_doc(uri: str) -> EmbeddedResource:
    return EmbeddedResource(
        uri=uri,
        text="Document content here...",
        mime_type="text/markdown"
    )
```

### Auto-Wrapping

If your tool returns a plain `str`, `dict`, `list`, `int`, `float`, or `bool`, it's automatically wrapped in `TextContent`. No need to import content types for simple cases.

---

## Automatic Schema Generation

micro_mcp introspects your function signatures and type hints to generate JSON Schema — **no Pydantic, no manual schemas**.

```python
@mcp.tool()
def search(query: str, limit: int = 10, exact: bool = False) -> str:
    ...
```

Auto-generates:
```json
{
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "limit": {"type": "integer"},
        "exact": {"type": "boolean"}
    },
    "required": ["query"]
}
```

- `query` has no default → **required**
- `limit` and `exact` have defaults → **optional**
- Types are mapped from Python annotations → JSON Schema types
- Dataclasses are recursively converted to nested object schemas

---

## Error Handling

micro_mcp uses standard JSON-RPC 2.0 and MCP error codes:

| Code | Name | When |
|---|---|---|
| `-32700` | Parse Error | Invalid JSON received |
| `-32600` | Invalid Request | Missing `jsonrpc` field, wrong version, etc. |
| `-32601` | Method Not Found | Unknown tool/resource/prompt name |
| `-32602` | Invalid Params | Missing required params, wrong types |
| `-32603` | Internal Error | Unhandled server exception |

**Tool errors** don't crash the server. If a tool handler raises an exception, the response includes `isError: true` with the error message:

```json
{
    "content": [{"type": "text", "text": "ValueError: invalid input"}],
    "isError": true
}
```

---

## VS Code Integration

### Workspace-level config

Create `.vscode/mcp.json` in your project:

```json
{
    "servers": {
        "my-server": {
            "type": "stdio",
            "command": "python",
            "args": ["${workspaceFolder}/my_server.py"],
            "env": {},
            "disabled": false
        }
    }
}
```

### SSE-based config

If your server runs as a standalone HTTP service:

```json
{
    "servers": {
        "my-server": {
            "type": "sse",
            "url": "http://localhost:8000/sse"
        }
    }
}
```

### Claude Desktop

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "my-server": {
            "command": "python",
            "args": ["C:/path/to/my_server.py"]
        }
    }
}
```

---

## Project Structure

```
micro_mcp/
├── __init__.py          # Public API — exports MCPServer, content types
├── server.py            # MCPServer class — decorator API + JSON-RPC dispatch
├── jsonrpc.py           # JSON-RPC 2.0 — parsing, serialization, construction
├── mcp_types.py         # Content types + JSON Schema from type hints
├── tools.py             # ToolRegistry — registration, schema gen, execution
├── resources.py         # ResourceRegistry — URI templates, matching, reading
├── prompts.py           # PromptRegistry — argument introspection, rendering
├── errors.py            # JSON-RPC + MCP error codes and exceptions
├── context.py           # MCPContext — per-request logging & progress
├── logger.py            # Stderr-only logger (keeps STDIO clean)
└── transport/
    ├── __init__.py
    ├── stdio.py         # STDIO transport (subprocess communication)
    └── sse.py           # SSE/HTTP transport (http.server based)
```

---

## Testing

The test suite uses Python's built-in `unittest` — no pytest needed.

```bash
# Run all tests
python -m unittest discover -s tests -v

# Run specific test modules
python -m unittest tests.test_jsonrpc -v
python -m unittest tests.test_tools -v
python -m unittest tests.test_resources -v
python -m unittest tests.test_prompts -v
python -m unittest tests.test_integration -v
python -m unittest tests.test_stdio_transport -v
```

**Test Coverage:**

| Module | Tests | What's Tested |
|---|---|---|
| `test_jsonrpc.py` | 17 | Parsing, serialization, errors, batch messages |
| `test_tools.py` | 14 | Registration, schema gen, sync/async execution, context injection |
| `test_resources.py` | 13 | Static/template resources, URI matching, binary content |
| `test_prompts.py` | 10 | Registration, argument introspection, rendering, validation |
| `test_integration.py` | 19 | Full MCP protocol flow: initialize → list → call → read |
| `test_stdio_transport.py` | 6 | Subprocess launch, JSON-RPC round-trips over STDIO |
| `test_sse_transport.py` | 1 | SSE endpoint validation (env-gated) |
| **Total** | **79** | ✅ All passing |

---

## API Reference

### `MCPServer`

```python
MCPServer(name: str = "micro_mcp", version: str = "1.0.0")
```

| Method / Decorator | Description |
|---|---|
| `@mcp.tool(name?, description?)` | Register a function as an MCP tool |
| `@mcp.resource(uri, *, name?, description?, mime_type?)` | Register a function as an MCP resource |
| `@mcp.prompt(name?, description?)` | Register a function as an MCP prompt |
| `@mcp.on_startup` | Register a startup hook |
| `@mcp.on_shutdown` | Register a shutdown hook |
| `mcp.run(transport="stdio")` | Start the server (`"stdio"` or `"sse"`) |
| `await mcp.handle_message(raw)` | Process a raw JSON-RPC string (for custom transports) |

### `MCPContext`

```python
MCPContext(request_id=None, server_name="micro_mcp", progress_callback=None)
```

| Method | Description |
|---|---|
| `ctx.info(msg)` | Log info to stderr |
| `ctx.warning(msg)` | Log warning to stderr |
| `ctx.error(msg)` | Log error to stderr |
| `ctx.debug(msg)` | Log debug to stderr |
| `ctx.report_progress(progress, total=1.0)` | Report progress to client |

### Content Types

| Class | Fields |
|---|---|
| `TextContent(text)` | Plain text content |
| `ImageContent(data, mime_type)` | Base64-encoded image |
| `EmbeddedResource(uri, text, mime_type?)` | Embedded resource reference |

---

## MCP Protocol Compliance

micro_mcp implements the following MCP methods:

| Method | Type | Supported |
|---|---|---|
| `initialize` | Request | ✅ |
| `initialized` | Notification | ✅ |
| `ping` | Request | ✅ |
| `tools/list` | Request | ✅ |
| `tools/call` | Request | ✅ |
| `resources/list` | Request | ✅ |
| `resources/read` | Request | ✅ |
| `resources/templates/list` | Request | ✅ |
| `prompts/list` | Request | ✅ |
| `prompts/get` | Request | ✅ |

**Protocol version:** `2024-11-05`

---

## Why micro_mcp?

| | micro_mcp | FastMCP |
|---|---|---|
| **Dependencies** | Zero | Pydantic, httpx, uvicorn, etc. |
| **Install size** | ~30 KB | Hundreds of MB |
| **Schema generation** | Python type hints | Pydantic models |
| **Learning curve** | Same decorator API | — |
| **Portability** | Copy a folder | pip install chain |
| **Python version** | 3.10+ | 3.10+ |

---

<p align="center">
  Built with ❤️ and zero <code>pip install</code>s
</p>
