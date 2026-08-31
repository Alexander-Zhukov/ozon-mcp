"""Domain errors surfaced to MCP callers."""

from __future__ import annotations


class OzonError(RuntimeError):
    """Base class for errors this server raises to the caller."""


class WritesDisabledError(OzonError):
    """Raised when a mutating tool is called while writes are disabled."""

    def __init__(self) -> None:
        super().__init__(
            "Account-mutating tools are disabled. Set OZON_ENABLE_WRITES=1 to allow cart / favorites / list changes."
        )
