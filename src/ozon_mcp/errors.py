"""Domain errors surfaced to MCP callers.

Each carries a ``code`` beside its message. The message is written to be relayed
to a person; the code is what a caller can branch on without matching text —
"session_expired" and "writes_disabled" call for different behaviour, and
telling them apart by substring is how a reworded sentence changes an agent's
mind about what to do.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    """What went wrong, in a form worth branching on."""

    OZON = "ozon_error"
    """Something Ozon refused that has no more specific code."""

    UPSTREAM = "upstream_unavailable"
    """Ozon did not answer with a readable page. Retrying may help."""

    RATE_LIMITED = "rate_limited"
    """Ozon is throttling this session. Waiting helps; retrying at once does not."""

    SESSION_EXPIRED = "session_expired"
    """The stored session is signed out; recovery needs a one-time code."""

    WRITES_DISABLED = "writes_disabled"
    """The operator has not allowed account changes. No tool can change that."""

    ORDERS_DISABLED = "orders_disabled"
    """The operator has not allowed placing orders. No tool can change that."""

    TOTAL_MISMATCH = "total_mismatch"
    """The confirmed total is no longer what Ozon charges. Nothing was ordered."""


class OzonError(RuntimeError):
    """Base class for errors this server raises to the caller.

    MCP hands a caller the message and nothing else, so the code is prefixed to
    it: a caller that wants to branch reads the prefix, and one that relays the
    text loses nothing worth keeping.
    """

    code: ErrorCode = ErrorCode.OZON

    def __init__(self, message: str) -> None:
        super().__init__(f"[{self.code}] {message}")


class UpstreamError(OzonError):
    """Ozon did not answer with a page this server can read.

    Raised instead of returning an empty one, because the two are
    indistinguishable downstream: every parser turns a page with no widgets into
    an empty list, so a 502 or a timeout used to surface as "you have no orders".
    """

    code = ErrorCode.UPSTREAM

    def __init__(self, status: int, detail: str = "") -> None:
        self.status = status
        described = f"HTTP {status}" if status else "no response"
        super().__init__(
            (
                f"Ozon did not return a readable page ({described}). Nothing was read, and this is not an "
                f"empty account — retry, and if it persists check whether the session or the network is at "
                f"fault. {detail}"
            ).strip()
        )


class RateLimitedError(UpstreamError):
    """Ozon is rate-limiting this session.

    Kept apart from other upstream failures because the answer is different:
    waiting helps, and the wait is the one Ozon asked for.
    """

    code = ErrorCode.RATE_LIMITED

    def __init__(self, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        waited = f" It asked to wait {retry_after:.0f}s." if retry_after else ""
        OzonError.__init__(
            self,
            f"Ozon is rate-limiting this session (HTTP 429) and the retries did not clear it.{waited} "
            "Nothing was read. Slow down or try again later.",
        )
        self.status = 429


class WritesDisabledError(OzonError):
    """Raised when a mutating tool is called while writes are disabled."""

    code = ErrorCode.WRITES_DISABLED

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

    code = ErrorCode.ORDERS_DISABLED

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

    code = ErrorCode.TOTAL_MISMATCH

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

    code = ErrorCode.SESSION_EXPIRED

    def __init__(self, detail: str = "") -> None:
        super().__init__(
            "The OZON session is signed out and no saved profile could restore it. "
            "To recover: call start_login(<account email or phone>), ask the user for the "
            "one-time code OZON sends, then call submit_login_code(<code>). "
            "Check session_status() to confirm. Until then no account data can be read"
            f"{detail}"
        )
