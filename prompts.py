"""
micro_mcp.prompts
~~~~~~~~~~~~~~~~~

Prompt registry — register Python functions as MCP prompt templates,
list them, and render them with dynamic arguments.

No external dependencies — pure Python stdlib only.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, get_type_hints

from .errors import InvalidParamsError, MethodNotFoundError
from .mcp_types import _get_description


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PromptArgument:
    """Describes a single argument accepted by a prompt.

    Attributes
    ----------
    name : str
        Parameter name.
    description : str
        Human-readable description (defaults to ``""``).
    required : bool
        Whether this argument must be provided.
    """

    name: str
    description: str = ""
    required: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
        }


@dataclass
class PromptInfo:
    """Metadata for a registered prompt.

    Attributes
    ----------
    name : str
        Unique prompt name.
    description : str
        Human-readable description.
    arguments : list[PromptArgument]
        The arguments this prompt accepts.
    handler : Callable
        The function that produces the prompt messages.
    """

    name: str
    description: str
    arguments: List[PromptArgument]
    handler: Callable


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class PromptRegistry:
    """Registry that stores and manages MCP prompts.

    Usage::

        registry = PromptRegistry()

        def summarize(text: str) -> list:
            \"\"\"Summarize the given text.\"\"\"
            return [{"role": "user", "content": f"Summarize: {text}"}]

        registry.register(summarize)
        result = registry.get("summarize", {"text": "Hello world"})
    """

    def __init__(self) -> None:
        self._prompts: Dict[str, PromptInfo] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        func: Callable,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> PromptInfo:
        """Register a callable as an MCP prompt.

        The function's parameters (excluding ``self``) become prompt
        arguments.  The function must return a list of message dicts,
        each with ``role`` and ``content`` keys.

        Parameters
        ----------
        func:
            The handler function.
        name:
            Override for the prompt name (defaults to ``func.__name__``).
        description:
            Override for the description (defaults to docstring).

        Returns
        -------
        PromptInfo
            The created prompt metadata.
        """
        prompt_name = name or func.__name__
        if prompt_name in self._prompts:
            raise ValueError(f"Prompt already registered: {prompt_name!r}")

        prompt_desc = description or _get_description(func)
        arguments = self._extract_arguments(func)

        info = PromptInfo(
            name=prompt_name,
            description=prompt_desc,
            arguments=arguments,
            handler=func,
        )
        self._prompts[prompt_name] = info
        return info

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_prompts(self) -> List[dict]:
        """Return prompts in MCP ``prompts/list`` response format.

        Returns
        -------
        list[dict]
            Each dict has ``name``, ``description``, and ``arguments``.
        """
        return [
            {
                "name": p.name,
                "description": p.description,
                "arguments": [a.to_dict() for a in p.arguments],
            }
            for p in self._prompts.values()
        ]

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def get(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> dict:
        """Render a prompt by name with the given arguments.

        Parameters
        ----------
        name:
            Prompt name.
        arguments:
            Named arguments to pass to the handler.

        Returns
        -------
        dict
            MCP ``GetPromptResult`` with ``description`` and ``messages``.

        Raises
        ------
        MethodNotFoundError
            If the prompt does not exist.
        InvalidParamsError
            If required arguments are missing.
        """
        if name not in self._prompts:
            raise MethodNotFoundError(f"Prompt not found: {name!r}")

        prompt = self._prompts[name]
        args = arguments or {}

        # Validate required arguments
        for arg in prompt.arguments:
            if arg.required and arg.name not in args:
                raise InvalidParamsError(
                    f"Missing required argument: {arg.name!r}"
                )

        # Call the handler
        raw_messages = prompt.handler(**args)

        # Normalize the output
        messages = self._normalize_messages(raw_messages)

        return {
            "description": prompt.description,
            "messages": messages,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_arguments(func: Callable) -> List[PromptArgument]:
        """Introspect a function to build the list of ``PromptArgument``s."""
        sig = inspect.signature(func)
        arguments: List[PromptArgument] = []

        for param_name, param in sig.parameters.items():
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            required = param.default is inspect.Parameter.empty
            arguments.append(
                PromptArgument(
                    name=param_name,
                    description="",
                    required=required,
                )
            )

        return arguments

    @staticmethod
    def _normalize_messages(raw: Any) -> List[dict]:
        """Normalize handler output to a list of MCP prompt messages.

        Each message must have ``role`` and ``content``.  If the content
        is a plain string it is wrapped in a ``TextContent`` block.
        """
        if not isinstance(raw, list):
            raw = [raw]

        messages: List[dict] = []
        for item in raw:
            if isinstance(item, dict):
                role = item.get("role", "user")
                content = item.get("content", "")
                # Normalize content to MCP content blocks
                if isinstance(content, str):
                    content = {"type": "text", "text": content}
                messages.append({"role": role, "content": content})
            elif isinstance(item, str):
                messages.append({
                    "role": "user",
                    "content": {"type": "text", "text": item},
                })
            else:
                messages.append({
                    "role": "user",
                    "content": {"type": "text", "text": str(item)},
                })

        return messages
