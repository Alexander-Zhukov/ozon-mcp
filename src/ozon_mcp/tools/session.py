"""Session state and the two-step interactive login."""

from typing import Annotated

from pydantic import Field

from ozon_mcp.dependencies import run_blocking
from ozon_mcp.mcp_server import mcp
from ozon_mcp.models.session import LoginStep, SessionStatus
from ozon_mcp.services import session


@mcp.tool()
async def session_status() -> SessionStatus:
    """Start here. Reports whether the stored session still acts as the account
    and what this server is allowed to do: writes_enabled covers cart,
    favorites and lists, orders_enabled covers placing an order. Both are the
    operator's settings and no tool can change them — plan around them.
    When signed_in is false, every other tool raises instead of answering,
    because a signed-out session otherwise looks exactly like an empty account:
    no orders, no balances, no explanation. Recovery is start_login() +
    submit_login_code(), and backup_available=true means it will most likely
    recover by itself on the next call.
    """
    return await run_blocking(session.session_status)


@mcp.tool()
async def start_login(
    login: Annotated[str, Field(description="The account's email or phone, as registered with Ozon.")],
) -> LoginStep:
    """Ask Ozon to send a one-time login code to `login` (account email or
    phone). Use this when session_status() reports signed_in=false and the kept
    profile copy did not recover it.
    Ozon delivers the code out of band (email, SMS or a flash call), so ask the
    user for it and pass it to submit_login_code().
    """
    return await run_blocking(lambda: session.start_login(login))


@mcp.tool()
async def submit_login_code(
    code: Annotated[str, Field(description="The one-time code Ozon sent; digits only, as received.")],
) -> SessionStatus:
    """Finish the login with the code Ozon sent, and keep a copy of the restored
    profile so the next sign-out costs nobody a code.
    Codes expire and are single-use: if it is refused, call start_login() again.
    """
    return await run_blocking(lambda: session.submit_login_code(code))
