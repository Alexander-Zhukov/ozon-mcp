"""Assembling the app: the server with every tool attached.

Importing a tool module is what registers its tools, so the assembly is one
place that imports them all. The instance itself lives in ``mcp_server``, which
lets a tool module import the server without the server importing the tools.
"""

from typing import Final

from mcp.server.fastmcp import FastMCP

from ozon_mcp.mcp_server import mcp as _server
from ozon_mcp.tools import cart, catalog, checkout, favorites, finance, orders, selections, session

# Naming the modules keeps the registration visible instead of leaving it to a
# side effect nobody can see.
TOOL_MODULES: Final = (orders, catalog, cart, favorites, selections, checkout, session, finance)


def build_server() -> FastMCP:
    """The server, with the tools of every module in ``TOOL_MODULES`` on it."""
    return _server


mcp: Final = build_server()
