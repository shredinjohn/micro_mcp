"""
micro_mcp.errors
~~~~~~~~~~~~~~~~

Standard JSON-RPC 2.0 and MCP error codes, plus custom exception classes.

All error codes follow the JSON-RPC 2.0 specification:
  https://www.jsonrpc.org/specification#error_object

No external dependencies — pure Python stdlib only.
"""


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 Standard Error Codes
# ---------------------------------------------------------------------------

PARSE_ERROR = -32700
"""Invalid JSON was received by the server."""

INVALID_REQUEST = -32600
"""The JSON sent is not a valid JSON-RPC Request object."""

METHOD_NOT_FOUND = -32601
"""The method does not exist or is not available."""

INVALID_PARAMS = -32602
"""Invalid method parameter(s)."""

INTERNAL_ERROR = -32603
"""Internal JSON-RPC error."""


# ---------------------------------------------------------------------------
# Exception Classes
# ---------------------------------------------------------------------------

class MCPError(Exception):
    """Base exception for all MCP framework errors.

    Attributes:
        code:    JSON-RPC numeric error code.
        message: Human-readable error description.
        data:    Optional additional error data.
    """

    def __init__(self, code: int, message: str, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict:
        """Serialize to a JSON-RPC error object."""
        err = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err

    def __repr__(self) -> str:
        return f"MCPError(code={self.code}, message={self.message!r})"


class ParseError(MCPError):
    """Raised when the incoming payload is not valid JSON."""

    def __init__(self, data=None):
        super().__init__(PARSE_ERROR, "Parse error", data)


class InvalidRequestError(MCPError):
    """Raised when the JSON is not a valid JSON-RPC request."""

    def __init__(self, data=None):
        super().__init__(INVALID_REQUEST, "Invalid Request", data)


class MethodNotFoundError(MCPError):
    """Raised when the requested method does not exist."""

    def __init__(self, method: str = ""):
        msg = f"Method not found: {method}" if method else "Method not found"
        super().__init__(METHOD_NOT_FOUND, msg)


class InvalidParamsError(MCPError):
    """Raised when method parameters are invalid."""

    def __init__(self, detail: str = ""):
        msg = f"Invalid params: {detail}" if detail else "Invalid params"
        super().__init__(INVALID_PARAMS, msg)


class InternalError(MCPError):
    """Raised for unexpected internal errors."""

    def __init__(self, detail: str = ""):
        msg = f"Internal error: {detail}" if detail else "Internal error"
        super().__init__(INTERNAL_ERROR, msg)
