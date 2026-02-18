"""
micro_mcp.logger
~~~~~~~~~~~~~~~~

Lightweight logging wrapper using Python's built-in ``logging`` module.

All log output is directed to **stderr** so it never interferes with the
STDIO transport, which uses stdout for JSON-RPC messages.

No external dependencies — pure Python stdlib only.
"""

import logging
import sys


def get_logger(name: str = "micro_mcp", level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger that writes to *stderr*.

    Parameters
    ----------
    name:
        Logger name (defaults to ``"micro_mcp"``).
    level:
        Logging level (defaults to ``logging.INFO``).

    Returns
    -------
    logging.Logger
        A configured logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers when called more than once.
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(level)
    return logger
