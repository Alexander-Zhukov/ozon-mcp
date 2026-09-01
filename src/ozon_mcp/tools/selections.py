"""«Подборки» — curated, publishable lists of products."""

from typing import Annotated

from pydantic import Field

from ozon_mcp.dependencies import run_blocking
from ozon_mcp.mcp_server import mcp
from ozon_mcp.models.common import WriteResult
from ozon_mcp.models.lists import Selection
from ozon_mcp.services import selections
from ozon_mcp.utils.annotations import Sku


@mcp.tool()
async def list_selections() -> list[Selection]:
    """The account's «Подборки» — curated, publishable lists of products, a
    different thing from the wishlists in get_lists().
    Each carries the uuid every other selection tool takes, how many products it
    holds, and Ozon's own status: "Личная подборка" while private, "N
    сохранений" once public, "На модерации" while a publication is being
    reviewed.
    """
    return await run_blocking(selections.list_selections)


@mcp.tool()
async def get_selection(
    uuid: Annotated[str, Field(description="The selection, from list_selections()[].uuid.")],
) -> Selection:
    """One «Подборка» in full: name, description, product count, status and
    `public` — whether it is published to the account's public profile.
    list_selections() does not carry the description or `public`; this does, and
    it is the only reliable read of visibility, because a selection under review
    is listed as "На модерации" either way.
    """
    return await run_blocking(lambda: selections.get_selection(uuid))


@mcp.tool()
async def create_selection(
    name: Annotated[
        str, Field(min_length=1, max_length=60, description="Name of the selection, as a person reads it.")
    ],
    sku: Sku,
    description: Annotated[str, Field(description="Optional text shown under the name.")] = "",
    public: Annotated[
        bool,
        Field(
            description="True publishes it to the account's public profile (goes through moderation). False keeps "
            "it visible only to whoever has the link."
        ),
    ] = False,
) -> Selection:
    """[GATED by writes_enabled] Create a «Подборка» around one product and
    return it with its uuid. More products go in with set_selection_items().
    `public` defaults to false on purpose: publishing puts it on the account
    owner's public profile, so ask them before passing true.
    """
    return await run_blocking(lambda: selections.create_selection(name, sku, description, public=public))


@mcp.tool()
async def set_selection_items(
    uuid: Annotated[str, Field(description="The selection, from list_selections()[].uuid.")],
    skus: Annotated[
        list[str],
        Field(description="The products the selection should hold, in full — not an addition."),
    ],
) -> Selection:
    """[GATED by writes_enabled] Set which products a selection holds.
    This replaces the list: to add, pass the current products plus the new one;
    to remove, pass the ones that should stay. An empty list empties it.
    Products must be in favorites first — Ozon draws only from there, and a
    product that is not is dropped silently, so check the `items` count that
    comes back.
    """
    return await run_blocking(lambda: selections.set_selection_items(uuid, skus))


@mcp.tool()
async def edit_selection(
    uuid: Annotated[str, Field(description="The selection, from list_selections()[].uuid.")],
    name: Annotated[str, Field(min_length=1, max_length=60, description="New name.")],
    description: Annotated[
        str | None,
        Field(description="New description. Omit to keep the current one — Ozon rewrites both together."),
    ] = None,
) -> Selection:
    """[GATED by writes_enabled] Rename a selection, and optionally replace its
    description. Visibility is preserved: an edit carries it, so a public
    selection stays public and a private one stays private.
    """
    return await run_blocking(lambda: selections.edit_selection(uuid, name, description))


@mcp.tool()
async def set_selection_public(
    uuid: Annotated[str, Field(description="The selection, from list_selections()[].uuid.")],
    public: Annotated[
        bool,
        Field(description="True publishes to the account's public profile, False takes it back to link-only."),
    ],
) -> Selection:
    """[GATED by writes_enabled] Publish a selection to the account owner's
    public profile, or unpublish it. Outward-facing — confirm with them before
    publishing. Publication is reviewed by Ozon, so the status comes back as
    "На модерации" rather than public.
    """
    return await run_blocking(lambda: selections.set_selection_public(uuid, public=public))


@mcp.tool()
async def delete_selection(
    uuid: Annotated[str, Field(description="The selection to delete, from list_selections()[].uuid.")],
) -> WriteResult:
    """[GATED by writes_enabled] Delete a «Подборка». The products in it are not
    deleted. Ozon's own warning: «Восстановить её не получится» — so confirm
    with the user first.
    """
    return await run_blocking(lambda: selections.delete_selection(uuid))
