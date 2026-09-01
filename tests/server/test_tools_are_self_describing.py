"""The schema and the descriptions are the whole documentation an agent gets.

Nothing else reaches it: not the README, not the docstrings of the services
underneath. So every tool describes itself, every argument describes itself, and
every closed set of values is an enum in the schema rather than prose the caller
has to parse.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ozon_mcp.main import mcp

if TYPE_CHECKING:
    from mcp.types import Tool

ENUM_ARGUMENTS = (
    ("list_orders", "scope"),
    ("purchases", "sort"),
    ("search", "sort"),
    ("select_cart_items", "mode"),
)
GATED_TOOLS = (
    "set_cart_quantity",
    "select_cart_items",
    "set_favorite",
    "set_list_membership",
    "place_order",
    "cancel_order",
)


def _properties(tool: Tool) -> dict[str, Any]:
    return (tool.inputSchema or {}).get("properties") or {}


def test_the_server_explains_itself() -> None:
    # Clients surface this on connect; it is where the flows are stated.
    instructions = mcp.instructions or ""
    assert "session_status()" in instructions
    assert "select_cart_items" in instructions
    assert "order_total" in instructions


async def test_every_tool_and_argument_describes_itself() -> None:
    tools = await mcp.list_tools()
    assert [tool.name for tool in tools if not (tool.description or "").strip()] == []
    undocumented = [
        f"{tool.name}.{name}"
        for tool in tools
        for name, spec in _properties(tool).items()
        if '"description"' not in json.dumps(spec)
    ]
    assert undocumented == []


async def test_closed_value_sets_are_enums_in_the_schema() -> None:
    by_name = {tool.name: tool for tool in await mcp.list_tools()}
    for tool_name, argument in ENUM_ARGUMENTS:
        spec = _properties(by_name[tool_name])[argument]
        assert spec.get("enum"), f"{tool_name}.{argument} should enumerate its values"


async def test_gated_tools_say_so_before_they_are_called() -> None:
    by_name = {tool.name: tool.description or "" for tool in await mcp.list_tools()}
    for name in GATED_TOOLS:
        assert "GATED" in by_name[name], name


async def test_money_tools_name_the_figure_to_quote() -> None:
    # Quoting today's charge on a deferred order tells the user it is free.
    by_name = {tool.name: tool.description or "" for tool in await mcp.list_tools()}
    assert "order_total" in by_name["get_checkout"]
    assert "order_total" in by_name["place_order"]
