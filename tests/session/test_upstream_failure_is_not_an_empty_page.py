"""A failed request must not look like an empty account.

Every parser turns a page with no widgets into an empty list, so returning
``{"widgetStates": {}}`` on a 502 or a timeout reported "you have no orders".
The tests drive the real request path with a stand-in for the HTTP session — the
seam the transport is built around — rather than patching its methods.
"""

from __future__ import annotations

from typing import Any, override

import pytest

from ozon_mcp.errors import RateLimitedError, UpstreamError
from ozon_mcp.session.transport import OzonSession
from ozon_mcp.utils.serde import dumps


class _Response:
    def __init__(self, status: int, text: str, headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self.text = text
        self.headers = headers or {}


class _Http:
    """Stands in for the curl_cffi session: hands back a scripted answer each call."""

    def __init__(self, *answers: _Response | Exception) -> None:
        self.answers = list(answers)
        self.calls = 0

    def request(self, *_args: Any, **_kwargs: Any) -> _Response:
        self.calls += 1
        answer = self.answers[min(self.calls, len(self.answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer


class _Session(OzonSession):
    """The transport with the browser side stubbed out."""

    def __init__(self, http: _Http) -> None:
        super().__init__()
        self._http = http
        self._headers = {"user-agent": "test"}
        self.rebootstraps = 0
        self.waits: list[tuple[int, float | None]] = []

    @override
    def _ensure_http(self) -> None:  # the browser is not part of these tests
        return

    @override
    def save_state(self) -> None:
        return

    @override
    def _rebootstrap(self) -> None:
        self.rebootstraps += 1

    @override
    def _sleep_before_retry(self, attempt: int, retry_after: float | None) -> None:
        self.waits.append((attempt, retry_after))


PAGE = dumps({"widgetStates": {"orderList-1": "{}"}})


def test_a_served_page_comes_back_parsed() -> None:
    session = _Session(_Http(_Response(200, PAGE)))
    page = session.fetch("/my/orderlist")
    assert page["widgetStates"]
    assert page["_httpStatus"] == 200


def test_a_server_error_raises_instead_of_answering_empty() -> None:
    session = _Session(_Http(_Response(502, "<html>bad gateway</html>")))
    with pytest.raises(UpstreamError) as raised:
        session.fetch("/my/orderlist")
    assert raised.value.status == 502
    # The message has to be relayable: it says nothing was read.
    assert "not an empty account" in str(raised.value)
    assert session._http.calls == 3


def test_a_transport_failure_raises_too() -> None:
    session = _Session(_Http(TimeoutError("connection timed out")))
    with pytest.raises(UpstreamError) as raised:
        session.fetch("/my/orderlist")
    assert raised.value.status == 0


def test_a_server_error_that_clears_is_retried_not_reported() -> None:
    session = _Session(_Http(_Response(500, "oops"), _Response(200, PAGE)))
    page = session.fetch("/my/orderlist")
    assert page["widgetStates"]
    assert session.waits == [(1, None)]


def test_a_rate_limit_honours_the_wait_ozon_asked_for() -> None:
    session = _Session(_Http(_Response(429, "slow down", {"Retry-After": "7"}), _Response(200, PAGE)))
    session.fetch("/my/orderlist")
    assert session.waits == [(1, pytest.approx(7.0))]


def test_a_rate_limit_that_does_not_clear_says_so() -> None:
    limited = _Response(429, "slow down", {"Retry-After": "3"})
    session = _Session(_Http(limited, limited, limited))
    with pytest.raises(RateLimitedError) as raised:
        session.fetch("/my/orderlist")
    assert raised.value.retry_after == pytest.approx(3.0)
    assert "rate-limiting" in str(raised.value)


def test_an_antibot_challenge_re_bootstraps_rather_than_waiting() -> None:
    session = _Session(_Http(_Response(403, '{"incidentId": "x"}'), _Response(200, PAGE)))
    session.fetch("/my/orderlist")
    assert session.rebootstraps == 1
    assert session.waits == []


def test_a_refused_action_is_passed_through_not_raised() -> None:
    # Ozon reports refused actions as JSON with a 4xx; the caller needs the
    # reason ("Пустое название вишлиста"), not an exception.
    body = dumps({"error": "Пустое название вишлиста"})
    session = _Session(_Http(_Response(400, body)))
    answer = session.action("favoriteCreateList", {"title": ""})
    assert answer["error"] == "Пустое название вишлиста"


def test_a_client_error_with_no_json_raises() -> None:
    # An HTML 404 carries nothing to act on, and would read as an empty page.
    session = _Session(_Http(_Response(404, "<html>not found</html>")))
    with pytest.raises(UpstreamError) as raised:
        session.fetch("/my/nope")
    assert raised.value.status == 404
