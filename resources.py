"""
micro_mcp.resources
~~~~~~~~~~~~~~~~~~~

Resource registry — register Python functions as MCP resources with URI
patterns (including URI templates), list them, and read their content.

No external dependencies — pure Python stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .errors import MethodNotFoundError
from .mcp_types import TextContent, _get_description


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ResourceInfo:
    """Metadata for a registered resource.

    Attributes
    ----------
    uri : str
        URI or URI template (e.g. ``"weather://{city}/current"``).
    name : str
        Human-readable name for the resource.
    description : str
        Description extracted from the docstring or provided explicitly.
    mime_type : str
        MIME type of the resource content.
    handler : Callable
        The function that produces the resource content.
    is_template : bool
        ``True`` if the URI contains ``{param}`` placeholders.
    """

    uri: str
    name: str
    description: str
    mime_type: str
    handler: Callable
    is_template: bool = False


# ---------------------------------------------------------------------------
# URI template helpers
# ---------------------------------------------------------------------------

# Matches ``{param}`` placeholders in URI templates.
_TEMPLATE_PARAM_RE = re.compile(r"\{(\w+)\}")


def _is_template(uri: str) -> bool:
    """Return ``True`` if *uri* contains ``{param}`` placeholders."""
    return bool(_TEMPLATE_PARAM_RE.search(uri))


def _template_to_regex(uri_template: str) -> re.Pattern:
    """Convert a URI template like ``weather://{city}/current`` into a
    compiled regex with named groups."""
    # Escape everything except the {param} placeholders
    parts = _TEMPLATE_PARAM_RE.split(uri_template)
    pattern_parts: List[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Literal segment — escape regex special chars
            pattern_parts.append(re.escape(part))
        else:
            # Named capture group for the parameter
            pattern_parts.append(f"(?P<{part}>[^/]+)")
    return re.compile("^" + "".join(pattern_parts) + "$")


def _match_uri(uri_template: str, uri: str) -> Optional[Dict[str, str]]:
    """Try to match *uri* against *uri_template*.

    Returns
    -------
    dict | None
        Matched parameter dict, or ``None`` if no match.
    """
    regex = _template_to_regex(uri_template)
    m = regex.match(uri)
    if m:
        return m.groupdict()
    return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ResourceRegistry:
    """Registry that stores and manages MCP resources.

    Usage::

        registry = ResourceRegistry()

        def get_data(city: str) -> str:
            \"\"\"Current weather data.\"\"\"
            return '{"temp": 22}'

        registry.register("weather://{city}/current", get_data)
        result = registry.read("weather://paris/current")
    """

    def __init__(self) -> None:
        self._resources: Dict[str, ResourceInfo] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        uri: str,
        func: Callable,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: str = "text/plain",
    ) -> ResourceInfo:
        """Register a callable as an MCP resource.

        Parameters
        ----------
        uri:
            URI or URI template string (e.g. ``"weather://{city}/current"``).
        func:
            The handler function.
        name:
            Override for the resource name (defaults to ``func.__name__``).
        description:
            Override for the description (defaults to docstring).
        mime_type:
            MIME type of the content (default ``"text/plain"``).

        Returns
        -------
        ResourceInfo
            The created resource metadata.
        """
        res_name = name or func.__name__
        res_desc = description or _get_description(func)

        info = ResourceInfo(
            uri=uri,
            name=res_name,
            description=res_desc,
            mime_type=mime_type,
            handler=func,
            is_template=_is_template(uri),
        )
        self._resources[uri] = info
        return info

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_resources(self) -> List[dict]:
        """Return non-template resources in MCP ``resources/list`` format."""
        return [
            {
                "uri": r.uri,
                "name": r.name,
                "description": r.description,
                "mimeType": r.mime_type,
            }
            for r in self._resources.values()
            if not r.is_template
        ]

    def list_templates(self) -> List[dict]:
        """Return resource templates in MCP ``resources/templates/list`` format."""
        return [
            {
                "uriTemplate": r.uri,
                "name": r.name,
                "description": r.description,
                "mimeType": r.mime_type,
            }
            for r in self._resources.values()
            if r.is_template
        ]

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read(self, uri: str) -> dict:
        """Read a resource by URI.

        For template resources, the URI is matched against all registered
        templates and the extracted parameters are passed to the handler.

        Parameters
        ----------
        uri:
            The concrete resource URI to read.

        Returns
        -------
        dict
            MCP ``ReadResourceResult`` with a ``contents`` list.

        Raises
        ------
        MethodNotFoundError
            If no matching resource is found.
        """
        # 1. Exact match (non-template)
        if uri in self._resources:
            res = self._resources[uri]
            if not res.is_template:
                content = res.handler()
                return self._wrap_content(uri, content, res.mime_type)

        # 2. Template match
        for res in self._resources.values():
            if not res.is_template:
                continue
            params = _match_uri(res.uri, uri)
            if params is not None:
                content = res.handler(**params)
                return self._wrap_content(uri, content, res.mime_type)

        raise MethodNotFoundError(f"Resource not found: {uri!r}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap_content(uri: str, content: Any, mime_type: str) -> dict:
        """Wrap raw handler output into an MCP ``ReadResourceResult``."""
        if isinstance(content, str):
            return {
                "contents": [
                    {"uri": uri, "text": content, "mimeType": mime_type}
                ]
            }
        if isinstance(content, bytes):
            import base64
            return {
                "contents": [
                    {
                        "uri": uri,
                        "blob": base64.b64encode(content).decode("ascii"),
                        "mimeType": mime_type,
                    }
                ]
            }
        # If it's already a dict with 'contents', pass through
        if isinstance(content, dict) and "contents" in content:
            return content
        # Fallback: stringify
        return {
            "contents": [
                {"uri": uri, "text": str(content), "mimeType": mime_type}
            ]
        }
