"""
micro_mcp.jsonrpc
~~~~~~~~~~~~~~~~~

Complete JSON-RPC 2.0 implementation — parsing, construction, serialization.

Covers requests, responses, notifications, batch messages, and error objects
according to the spec at https://www.jsonrpc.org/specification.

No external dependencies — pure Python stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .errors import (
    InvalidRequestError,
    MCPError,
    ParseError,
)

# JSON-RPC version constant
JSONRPC_VERSION = "2.0"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class JSONRPCRequest:
    """A JSON-RPC 2.0 request (expects a response).

    Attributes
    ----------
    method : str
        Name of the method to invoke.
    id : Any
        Unique request identifier (str or int).
    params : dict | list | None
        Positional or named parameters.
    """

    method: str
    id: Any = None
    params: Optional[Union[Dict[str, Any], List[Any]]] = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-RPC request dict."""
        d: Dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": self.method}
        if self.id is not None:
            d["id"] = self.id
        if self.params is not None:
            d["params"] = self.params
        return d


@dataclass
class JSONRPCNotification:
    """A JSON-RPC 2.0 notification (no ``id``, no response expected).

    Attributes
    ----------
    method : str
        Notification method name.
    params : dict | list | None
        Positional or named parameters.
    """

    method: str
    params: Optional[Union[Dict[str, Any], List[Any]]] = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-RPC notification dict."""
        d: Dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": self.method}
        if self.params is not None:
            d["params"] = self.params
        return d


@dataclass
class JSONRPCError:
    """A JSON-RPC 2.0 error object.

    Attributes
    ----------
    code : int
        Numeric error code.
    message : str
        Short description of the error.
    data : Any
        Optional additional information about the error.
    """

    code: int
    message: str
    data: Any = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-RPC error dict."""
        d: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


@dataclass
class JSONRPCResponse:
    """A JSON-RPC 2.0 response.

    Exactly one of ``result`` or ``error`` must be set.

    Attributes
    ----------
    id : Any
        The request identifier this response corresponds to.
    result : Any
        The result of the method call (on success).
    error : JSONRPCError | None
        The error object (on failure).
    """

    id: Any
    result: Any = None
    error: Optional[JSONRPCError] = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-RPC response dict."""
        d: Dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "id": self.id}
        if self.error is not None:
            d["error"] = self.error.to_dict()
        else:
            d["result"] = self.result
        return d


# ---------------------------------------------------------------------------
# Helpers: construction shortcuts
# ---------------------------------------------------------------------------

def make_response(request_id: Any, result: Any) -> JSONRPCResponse:
    """Create a success response for the given *request_id*."""
    return JSONRPCResponse(id=request_id, result=result)


def make_error_response(
    request_id: Any,
    code: int,
    message: str,
    data: Any = None,
) -> JSONRPCResponse:
    """Create an error response for the given *request_id*."""
    return JSONRPCResponse(
        id=request_id,
        error=JSONRPCError(code=code, message=message, data=data),
    )


def make_error_response_from_exc(
    request_id: Any,
    exc: MCPError,
) -> JSONRPCResponse:
    """Create an error response directly from an ``MCPError``."""
    return JSONRPCResponse(
        id=request_id,
        error=JSONRPCError(code=exc.code, message=exc.message, data=exc.data),
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_message(raw: str) -> Union[JSONRPCRequest, JSONRPCNotification, List]:
    """Parse a raw JSON string into a JSON-RPC message object.

    Parameters
    ----------
    raw : str
        Raw JSON string (single message or batch array).

    Returns
    -------
    JSONRPCRequest | JSONRPCNotification | list
        Parsed message(s).

    Raises
    ------
    ParseError
        If the string is not valid JSON.
    InvalidRequestError
        If the JSON does not conform to JSON-RPC 2.0.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ParseError(str(exc))

    # Batch request
    if isinstance(data, list):
        if not data:
            raise InvalidRequestError("Empty batch array")
        return [_parse_single(item) for item in data]

    return _parse_single(data)


def _parse_single(data: Any) -> Union[JSONRPCRequest, JSONRPCNotification]:
    """Parse a single JSON-RPC message dict."""
    if not isinstance(data, dict):
        raise InvalidRequestError("Message must be a JSON object")

    # Validate jsonrpc version
    if data.get("jsonrpc") != JSONRPC_VERSION:
        raise InvalidRequestError(
            f"Unsupported jsonrpc version: {data.get('jsonrpc')!r}"
        )

    method = data.get("method")
    if not isinstance(method, str):
        raise InvalidRequestError("'method' must be a string")

    params = data.get("params")
    if params is not None and not isinstance(params, (dict, list)):
        raise InvalidRequestError("'params' must be an object or array")

    # Notifications have no "id" key at all
    if "id" not in data:
        return JSONRPCNotification(method=method, params=params)

    return JSONRPCRequest(method=method, id=data["id"], params=params)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def serialize(msg: Union[JSONRPCRequest, JSONRPCNotification, JSONRPCResponse, dict]) -> str:
    """Serialize a JSON-RPC object to a JSON string.

    Parameters
    ----------
    msg:
        A JSON-RPC dataclass or raw dict.

    Returns
    -------
    str
        Compact JSON string (no trailing newline).
    """
    if isinstance(msg, dict):
        return json.dumps(msg, separators=(",", ":"))
    return json.dumps(msg.to_dict(), separators=(",", ":"))
