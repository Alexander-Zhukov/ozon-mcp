"""Dependency-injection factories (no bare module-level singletons)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from typing import TYPE_CHECKING

from ozon_mcp.session.transport import OzonSession

if TYPE_CHECKING:
    from collections.abc import Callable


@cache
def get_session() -> OzonSession:
    """The process-wide OZON session; disposed via ``get_session.cache_clear()``."""
    return OzonSession()


@cache
def get_executor() -> ThreadPoolExecutor:
    """The one thread every session operation runs on.

    Two constraints force a single dedicated thread: Playwright's sync API
    refuses to run inside a live asyncio loop (which is where the MCP server
    dispatches tools), and its objects may only be touched from the thread that
    created them — so a pool of interchangeable workers would break browser
    reuse. One worker also serialises access, matching the session's own lock.
    """
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="ozon-session")


async def run_blocking[T](work: Callable[[], T]) -> T:
    """Await blocking session work off the event loop."""
    return await asyncio.get_running_loop().run_in_executor(get_executor(), work)
