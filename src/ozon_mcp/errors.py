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


class TotalMismatchError(OzonError):
    """The total confirmed by the caller is not the total Ozon is charging.

    Ozon recalculates a pending order on its own (prices, delivery), so a total
    read a minute ago may be stale. Refusing beats charging a different amount
    than the one the user agreed to.
    """

    def __init__(self, expected: str, actual: str | None) -> None:
        super().__init__(f"order total is {actual!r}, not the confirmed {expected!r}; re-read get_checkout()")


class SessionExpiredError(OzonError):
    """The stored session is signed out and could not be restored.

    Raised instead of returning empty results, which is what a signed-out
    session otherwise looks like: orders vanish, balances read as None, and
    nothing says why. The message is written for whoever is driving the agent,
    because recovery needs a one-time code that only the account owner receives.
    """

    def __init__(self, detail: str = "") -> None:
        super().__init__(
            "The OZON session is signed out and no saved profile could restore it. "
            "To recover: call start_login(<account email or phone>), ask the user for the "
            "one-time code OZON sends, then call submit_login_code(<code>). "
            "Check session_status() to confirm. Until then no account data can be read"
            f"{detail}"
        )
