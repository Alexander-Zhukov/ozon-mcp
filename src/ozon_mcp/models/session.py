"""Session and login DTOs."""

from __future__ import annotations

from ozon_mcp.models.base import OzonModel


class SessionStatus(OzonModel):
    """Whether the stored session can still act as the account.

    ``backup_available`` matters when it cannot: a kept copy is restored
    automatically, so a signed-out session with a backup usually recovers
    without anyone being asked for a code.
    """

    signed_in: bool = False
    user_id: str | None = None
    backup_available: bool = False
    detail: str | None = None


class LoginStep(OzonModel):
    """Where an interactive login has got to.

    Ozon sends a one-time code out of band, so the login is necessarily two
    calls with a person in between; ``stage`` says which one is due.
    """

    stage: str
    login: str | None = None
    detail: str | None = None
