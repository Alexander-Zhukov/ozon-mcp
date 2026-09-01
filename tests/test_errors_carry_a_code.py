"""An error's code is what a caller branches on; its text is what a person reads."""

from ozon_mcp.errors import (
    ErrorCode,
    OrdersDisabledError,
    OzonError,
    RateLimitedError,
    SessionExpiredError,
    TotalMismatchError,
    UpstreamError,
    WritesDisabledError,
)


def test_every_error_names_itself() -> None:
    assert OzonError("что-то").code is ErrorCode.OZON
    assert UpstreamError(502).code is ErrorCode.UPSTREAM
    assert RateLimitedError(3.0).code is ErrorCode.RATE_LIMITED
    assert WritesDisabledError().code is ErrorCode.WRITES_DISABLED
    assert OrdersDisabledError().code is ErrorCode.ORDERS_DISABLED
    assert TotalMismatchError("1 ₽", "2 ₽").code is ErrorCode.TOTAL_MISMATCH
    assert SessionExpiredError().code is ErrorCode.SESSION_EXPIRED


def test_the_code_travels_with_the_message() -> None:
    # MCP hands the caller a string and nothing else.
    assert str(WritesDisabledError()).startswith("[writes_disabled]")
    assert "operator's setting" in str(WritesDisabledError())


def test_the_message_still_says_what_to_do() -> None:
    expired = str(SessionExpiredError())
    assert "start_login" in expired
    assert "submit_login_code" in expired
    mismatch = str(TotalMismatchError("999 ₽", "777 ₽"))
    assert "Nothing was ordered" in mismatch
    assert "777 ₽" in mismatch
