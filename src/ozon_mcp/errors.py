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


class OrdersDisabledError(OzonError):
    """Placing an order is gated separately from other writes: it spends money
    and cannot be undone through this server.
    """

    def __init__(self) -> None:
        super().__init__("Order placement is disabled; set OZON_ENABLE_ORDERS=1 to allow it.")
