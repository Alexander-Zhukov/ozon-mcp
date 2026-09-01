"""A profile copied while Chromium runs is a copy of the session before it.

Chromium holds its cookie jar in memory and writes it out on exit, so backing
up a live profile snapshotted the pre-login state — the bug that made a fresh
sign-in come back as a guest one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ozon_mcp.session.transport import OzonSession

if TYPE_CHECKING:
    from pathlib import Path


class _Session(OzonSession):
    """Records the order of the two operations that have to be ordered."""

    def __init__(self, profile: Path, backup: Path) -> None:
        self.calls: list[str] = []
        self._profile = profile
        self._backup = backup

    def _close_browser(self) -> None:
        self.calls.append("close")


def test_the_browser_is_closed_before_the_copy(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    (profile / "Default").mkdir(parents=True)
    (profile / "Default" / "Cookies").write_text("jar", encoding="utf-8")
    (profile / "SingletonLock").write_text("lock", encoding="utf-8")

    session = _Session(profile, tmp_path / "profile.backup")
    session.back_up_profile()

    assert session.calls == ["close"]
    assert (tmp_path / "profile.backup" / "Default" / "Cookies").read_text(encoding="utf-8") == "jar"
    # The lock belongs to the process that held it, not to the copy.
    assert not (tmp_path / "profile.backup" / "SingletonLock").exists()


def test_a_missing_profile_is_not_an_error(tmp_path: Path) -> None:
    session = _Session(tmp_path / "gone", tmp_path / "backup")
    session.back_up_profile()
    assert session.calls == ["close"]
    assert not (tmp_path / "backup").exists()
