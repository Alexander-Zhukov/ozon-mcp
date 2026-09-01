"""Domain errors surfaced to MCP callers."""

from __future__ import annotations


class OzonError(RuntimeError):
    """Base class for errors this server raises to the caller."""


class WritesDisabledError(OzonError):
    """Raised when a mutating tool is called while writes are disabled."""

    def __init__(self) -> None:
        super().__init__(
            "Account-mutating tools are disabled: the cart, favorites and lists cannot be changed. "
            "This is the operator's setting (OZON_ENABLE_WRITES=1) and no tool can change it — "
            "say so instead of retrying, and read session_status() to see both gates upfront."
        )


class OrdersDisabledError(OzonError):
    """Placing an order is gated separately from other writes: it spends money
    and cannot be undone through this server.
    """

    def __init__(self) -> None:
        super().__init__(
            "Placing an order is disabled, separately from other writes, because it spends real money. "
            "This is the operator's setting (OZON_ENABLE_ORDERS=1) and no tool can change it: the order can "
            "still be composed and priced with get_checkout(), but not submitted. Report that and stop."
        )


class TotalMismatchError(OzonError):
    """The total confirmed by the caller is not the total Ozon is charging.

    Ozon recalculates a pending order on its own (prices, delivery), so a total
    read a minute ago may be stale. Refusing beats charging a different amount
    than the one the user agreed to.
    """

    def __init__(self, expected: str, actual: str | None) -> None:
        super().__init__(
            f"the order now costs {actual!r}, not the confirmed {expected!r} — Ozon recalculated it. "
            "Nothing was ordered. Re-read get_checkout(), show the user totals.order_total, and "
            "call place_order() again with the figure they agreed to."
        )


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
