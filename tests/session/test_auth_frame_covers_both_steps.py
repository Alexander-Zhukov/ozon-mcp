"""A login begun in one call has to be completable in the next.

Ozon swaps the iframe between the two steps, and matching only the first URL
made the code step read as a vanished login form.
"""

from __future__ import annotations

import pytest

from ozon_mcp.session.transport import _is_auth_frame


@pytest.mark.parametrize(
    "url",
    [
        "https://www.ozon.ru/ozonid-lite?token=eyJhbGciOiJIUzI1NiJ9",
        "https://www.ozon.ru/ozonid-lite?redirect=https%3A%2F%2Fwww.ozon.ru%2Fmy%2Forderlist&token=x",
        "https://www.ozon.ru/otp-lite?token=6a2ced29-51a9-462a-a180-a99d53f1290b",
    ],
)
def test_both_login_steps_are_recognised(url: str) -> None:
    assert _is_auth_frame(url) is True


@pytest.mark.parametrize(
    "url",
    ["https://www.ozon.ru/my/orderlist", "https://www.ozon.ru/", "about:blank"],
)
def test_ordinary_pages_are_not_login_frames(url: str) -> None:
    assert _is_auth_frame(url) is False
