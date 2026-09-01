"""Session state and interactive re-login.

A signed-out session is indistinguishable from an empty account: orders come
back empty, balances read as None, nothing explains why. So the state is
reportable, a signed-out session raises rather than answers, and recovery is
available as tools — Ozon sends a one-time code out of band, so it takes two
calls with a person in between.
"""

from __future__ import annotations

from ozon_mcp.dependencies import get_session
from ozon_mcp.models.session import LoginStep, SessionStatus


def session_status() -> SessionStatus:
    """Whether the stored session still acts as the account."""
    session = get_session()
    user = session.signed_in_user()
    backup = session.has_backup()
    if user:
        return SessionStatus(signed_in=True, user_id=user, backup_available=backup)
    return SessionStatus(
        signed_in=False,
        backup_available=backup,
        detail=(
            "signed out; a kept profile copy is tried automatically on the next call"
            if backup
            else "signed out and no profile copy kept — start_login() is needed"
        ),
    )


def start_login(login: str) -> LoginStep:
    """Ask Ozon to send a one-time code to ``login`` (email or phone)."""
    channel = get_session().begin_login(login)
    return LoginStep(
        stage="code_requested",
        login=login,
        detail=f"Ozon is sending a code by {channel}; pass it to submit_login_code()",
    )


def submit_login_code(code: str) -> SessionStatus:
    """Finish the login with the code Ozon sent, and keep a copy of the profile."""
    session = get_session()
    if not session.complete_login(code):
        return SessionStatus(
            signed_in=False,
            backup_available=session.has_backup(),
            detail="the code was not accepted; request a new one with start_login()",
        )
    return SessionStatus(
        signed_in=True,
        user_id=session.signed_in_user(),
        backup_available=session.has_backup(),
        detail="signed in; the profile was backed up",
    )
