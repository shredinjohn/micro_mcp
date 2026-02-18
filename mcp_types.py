"""
micro_mcp.types
~~~~~~~~~~~~~~~

MCP content types and automatic JSON Schema generation from Python type hints.

Converts function signatures into JSON Schema ``inputSchema`` objects without
any third-party library — relies solely on ``inspect`` and ``typing``.

No external dependencies — pure Python stdlib only.
"""

from __future__ import annotations

import inspect
import typing
from dataclasses import dataclass, field, asdict
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    Union,
    get_type_hints,
)


# ---------------------------------------------------------------------------
# MCP Content Types
# ---------------------------------------------------------------------------

@dataclass
class TextContent:
    """Plain-text content block returned by tools/resources.

    Attributes
    ----------
    text : str
        The textual content.
    type : str
        Always ``"text"``.
    """

    text: str
    type: str = "text"

    def to_dict(self) -> dict:
        return {"type": self.type, "text": self.text}


@dataclass
class ImageContent:
    """Base64-encoded image content block.

    Attributes
    ----------
    data : str
        Base64-encoded image data.
    mime_type : str
        MIME type (e.g. ``"image/png"``).
    type : str
        Always ``"image"``.
    """

    data: str
    mime_type: str
    type: str = "image"

    def to_dict(self) -> dict:
        return {"type": self.type, "data": self.data, "mimeType": self.mime_type}


@dataclass
class EmbeddedResource:
    """Embedded resource content — wraps a resource reference with its data.

    Attributes
    ----------
    uri : str
        The resource URI.
    text : str
        The resource text content.
    mime_type : str
        MIME type of the resource.
    type : str
        Always ``"resource"``.
    """

    uri: str
    text: str
    mime_type: str = "text/plain"
    type: str = "resource"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "resource": {
                "uri": self.uri,
                "text": self.text,
                "mimeType": self.mime_type,
            },
        }


# ---------------------------------------------------------------------------
# JSON Schema generation from Python types
# ---------------------------------------------------------------------------

def _python_type_to_json_schema(annotation: Any) -> dict:
    """Convert a single Python type annotation to a JSON Schema fragment.

    Handles primitive types, ``Optional``, ``Union``, ``list``, ``dict``,
    ``tuple``, and dataclasses (recursively).

    Parameters
    ----------
    annotation : Any
        A Python type annotation (e.g. ``str``, ``list[int]``,
        ``Optional[str]``).

    Returns
    -------
    dict
        JSON Schema fragment.
    """
    # Handle NoneType
    if annotation is type(None):
        return {"type": "null"}

    # Primitives
    _PRIMITIVES = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
    }
    if annotation in _PRIMITIVES:
        return dict(_PRIMITIVES[annotation])

    # ``Any`` — no schema constraint
    if annotation is Any:
        return {}

    # Get the origin for generic types (list, dict, Optional, Union, etc.)
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    # --- Optional[X] is Union[X, None] ---
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            # Optional[X]
            schema = _python_type_to_json_schema(non_none[0])
            return schema
        # Generic Union
        return {"anyOf": [_python_type_to_json_schema(a) for a in args]}

    # --- list[X] ---
    if origin is list:
        schema: dict = {"type": "array"}
        if args:
            schema["items"] = _python_type_to_json_schema(args[0])
        return schema

    # --- dict[K, V] ---
    if origin is dict:
        schema = {"type": "object"}
        if len(args) >= 2:
            schema["additionalProperties"] = _python_type_to_json_schema(args[1])
        return schema

    # --- tuple[X, Y, ...] ---
    if origin is tuple:
        schema = {"type": "array"}
        if args:
            schema["items"] = [_python_type_to_json_schema(a) for a in args]
        return schema

    # --- Dataclass → nested object schema ---
    if hasattr(annotation, "__dataclass_fields__"):
        return _dataclass_to_schema(annotation)

    # Fallback: treat as string
    return {"type": "string"}


def _dataclass_to_schema(cls: type) -> dict:
    """Generate a JSON Schema ``object`` for a dataclass.

    Parameters
    ----------
    cls : type
        A Python ``@dataclass``-decorated class.

    Returns
    -------
    dict
        JSON Schema of type ``"object"`` with properties for each field.
    """
    hints = get_type_hints(cls)
    properties: Dict[str, dict] = {}
    required: List[str] = []

    for name, type_hint in hints.items():
        properties[name] = _python_type_to_json_schema(type_hint)
        # If the field has no default, it's required
        dc_field = cls.__dataclass_fields__.get(name)
        if dc_field is not None:
            has_default = (
                dc_field.default is not dc_field.default_factory  # type: ignore[attr-defined]
                if dc_field.default is inspect.Parameter.empty
                else True
            )
            if dc_field.default is inspect.Parameter.empty and dc_field.default_factory is inspect.Parameter.empty:  # type: ignore[attr-defined]
                required.append(name)
        else:
            required.append(name)

    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


# ---------------------------------------------------------------------------
# Public API: generate_schema
# ---------------------------------------------------------------------------

def generate_schema(func: Callable) -> dict:
    """Introspect a callable's signature and type hints to produce a JSON
    Schema suitable for the MCP ``inputSchema`` field.

    Parameters
    ----------
    func : Callable
        The tool/resource/prompt handler function.

    Returns
    -------
    dict
        A JSON Schema object (``{"type": "object", "properties": {...}, ...}``).

    Example
    -------
    >>> def greet(name: str, age: int = 25) -> str: ...
    >>> generate_schema(greet)
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"}
        },
        "required": ["name"]
    }
    """
    sig = inspect.signature(func)
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    properties: Dict[str, dict] = {}
    required: List[str] = []

    for param_name, param in sig.parameters.items():
        # Skip *args, **kwargs, and the special 'ctx' context parameter
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if param_name == "ctx":
            continue

        # Determine annotation
        annotation = hints.get(param_name, param.annotation)
        if annotation is inspect.Parameter.empty:
            annotation = str  # default to string if no annotation

        properties[param_name] = _python_type_to_json_schema(annotation)

        # Add description from default if it's a specific sentinel (N/A here).
        # A parameter is required if it has no default value.
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _get_description(func: Callable) -> str:
    """Extract a description from a function's docstring.

    Uses the first non-empty line of the docstring.

    Parameters
    ----------
    func : Callable
        The function to inspect.

    Returns
    -------
    str
        The extracted description, or an empty string.
    """
    doc = inspect.getdoc(func)
    if not doc:
        return ""
    # Return first non-blank line
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""
