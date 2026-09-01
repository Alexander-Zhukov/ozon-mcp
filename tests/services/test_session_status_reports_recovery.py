"""A signed-out session must say so, and say whether it can self-heal."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ozon_mcp.services.session import session_status

if TYPE_CHECKING:
    import pytest


class _FakeSession:
    def __init__(self, user: str | None, *, backup: bool) -> None:
        self._user, self._backup = user, backup

    def signed_in_user(self) -> str | None:
        return self._user

    def has_backup(self) -> bool:
        return self._backup


def test_signed_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ozon_mcp.services.session.get_session", lambda: _FakeSession("44563249", backup=True))
    status = session_status()
    assert status.signed_in is True
    assert status.user_id == "44563249"


def test_signed_out_with_a_backup_says_it_will_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ozon_mcp.services.session.get_session", lambda: _FakeSession(None, backup=True))
    status = session_status()
    assert status.signed_in is False
    assert status.detail is not None
    assert "automatically" in status.detail


def test_signed_out_without_a_backup_asks_for_a_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ozon_mcp.services.session.get_session", lambda: _FakeSession(None, backup=False))
    status = session_status()
    assert status.detail is not None
    assert "start_login" in status.detail
