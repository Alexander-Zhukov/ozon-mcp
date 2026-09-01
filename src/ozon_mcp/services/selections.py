"""«Подборки» — curated, publishable lists of products.

A separate entity from wishlists, with its own identifiers and its own rules:

- a selection is addressed by a uuid, and reading one also needs its owner id,
  which only the list's link carries;
- its products come from favorites — Ozon's own picker offers nothing else, so a
  product has to be favorited before it can be put in a selection;
- one call sets the whole product list rather than appending to it, which is
  also how a product is taken out;
- it can be published to the account's public profile, and publishing goes
  through moderation, so the state right after is "На модерации" and not "live".

All of it is driven by one action, ``submitSelectionFormWeb``, told apart by its
``placement``: creating, editing the text and setting the products are three
different placements of the same call, and passing the wrong one silently
creates a second selection instead of changing the first.
"""

from __future__ import annotations

import re
from typing import Any, Final

from ozon_mcp.dependencies import get_session
from ozon_mcp.errors import OzonError, WritesDisabledError
from ozon_mcp.models.common import WriteResult
from ozon_mcp.models.lists import Selection
from ozon_mcp.parsing.common import widget
from ozon_mcp.parsing.selections import parse_selections
from ozon_mcp.settings import get_settings

_SUBMIT_ACTION: Final = "submitSelectionFormWeb"
_DELETE_ACTION: Final = "deleteSelection"
_PUBLIC_ACTION: Final = "setSelectionPublicStatus"
_CREATE: Final = "create_fields"
_EDIT_TEXT: Final = "update_fields"
_SET_ITEMS: Final = "update_items"
# The list lives in a container the page fetches after itself; asking for the
# page alone returns a shell with no selections in it.
_LIST_PATH: Final = "/selections/list?layout_container=list_selections_next_container&layout_page_index=2"
_PRIVATE_STATUS: Final = "Личная подборка"
_UID_RE: Final = re.compile(r"uId=([0-9a-f-]{36})")
# The edit form is the only place that states a selection's own fields back.
_FORM_PATH: Final = "/selections/form?form_mode=edit&sId={uuid}"
_FORM_WIDGET: Final = "webSelectionItemForm"


def _require_writes() -> None:
    if not get_settings().enable_writes:
        raise WritesDisabledError


def _complaint(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    said = response.get("errorForUser") or response.get("error")
    return str(said) if said else None


def list_selections() -> list[Selection]:
    """Every selection the account owns, with its size, status and ids."""
    return parse_selections(get_session().fetch(_LIST_PATH, backend="entrypoint"))


def get_selection(uuid: str) -> Selection:
    """One selection with everything about it, including its visibility.

    Visibility and description come from the edit form, which is the only place
    Ozon states a selection's own fields back. The list cannot stand in for it:
    a selection under review is listed as "На модерации" whether it is public or
    not, so a caller deciding from the status alone would get it wrong half the
    time.
    """
    listed = _find(str(uuid))
    form = widget(get_session().fetch(_FORM_PATH.format(uuid=uuid)), _FORM_WIDGET) or {}
    fields = form.get("form") if isinstance(form, dict) else None
    fields = fields if isinstance(fields, dict) else {}
    cell: dict[str, Any] = fields.get("anonymousCell") or {}
    right: dict[str, Any] = cell.get("rightBlock") or {} if isinstance(cell, dict) else {}
    control: dict[str, Any] = right.get("control") or {} if isinstance(right, dict) else {}
    toggle = control.get("toggle") if isinstance(control, dict) else None
    title_area: dict[str, Any] = fields.get("titleArea") or {}
    description_area: dict[str, Any] = fields.get("descriptionArea") or {}
    title = title_area.get("text") if isinstance(title_area, dict) else None
    description = description_area.get("text") if isinstance(description_area, dict) else None
    return listed.model_copy(
        update={
            "name": str(title) if isinstance(title, str) else listed.name,
            "description": str(description) if isinstance(description, str) else None,
            "public": bool(toggle.get("isSelected")) if isinstance(toggle, dict) else None,
        }
    )


def _find(uuid: str) -> Selection:
    for selection in list_selections():
        if selection.uuid == uuid:
            return selection
    msg = f"no selection {uuid} in this account"
    raise OzonError(msg)


def create_selection(name: str, sku: str, description: str = "", *, public: bool = False) -> Selection:
    """Create a selection holding one product, and return it with its uuid.

    A product is required because Ozon builds the selection around it; more are
    added afterwards with ``set_selection_items``. ``public`` false keeps it off
    the account's public profile — visible only to whoever has the link — which
    is the safer default for something created on someone's behalf.
    """
    _require_writes()
    response = get_session().action(
        _SUBMIT_ACTION,
        {
            "placement": _CREATE,
            "prefilledSku": str(sku),
            "selectionUuid": "",
            "media": [],
            "content": {"title": name, "description": description, "isPublic": "true" if public else "false"},
        },
    )
    said = _complaint(response)
    uuid = response.get("selectionUuid") if isinstance(response, dict) else None
    if said or not uuid:
        msg = f"Ozon refused to create the selection: {said or 'no uuid came back'}"
        raise OzonError(msg)
    owner = _UID_RE.search(str((response.get("action") or {}).get("link") or ""))
    return Selection(
        uuid=str(uuid),
        owner_id=owner.group(1) if owner else None,
        name=name,
        items=1,
        status="На модерации" if public else _PRIVATE_STATUS,
        public=public,
    )


def edit_selection(uuid: str, name: str, description: str | None = None) -> Selection:
    """Rename a selection, and optionally replace its description.

    Uses the edit placement deliberately: the same call with the create
    placement and a uuid does not fail — it creates a second selection with the
    new name, leaving the original untouched and the caller none the wiser.

    The visibility travels with the text, so it is read first and sent back
    unchanged: an edit that omitted it would quietly unpublish a public
    selection, and one that assumed a value would publish a private one. The
    description travels with it too, which is why leaving it out keeps the
    current one rather than clearing it.
    """
    _require_writes()
    current = get_selection(str(uuid))
    response = get_session().action(
        _SUBMIT_ACTION,
        {
            "placement": _EDIT_TEXT,
            "selectionUuid": str(uuid),
            "media": [],
            "content": {
                "title": name,
                "description": current.description or "" if description is None else description,
                "isPublic": "true" if current.public else "false",
            },
            "prefilledSku": None,
        },
    )
    said = _complaint(response)
    if said:
        msg = f"Ozon refused to edit the selection: {said}"
        raise OzonError(msg)
    return get_selection(str(uuid))


def set_selection_items(uuid: str, skus: list[str]) -> Selection:
    """Set which products a selection holds — the whole list, not an addition.

    Ozon sends the full set on every change, so this is how a product is added
    *and* how one is removed: pass the products that should remain. They must be
    in favorites, because that is the only place Ozon's own picker draws from,
    and one that is not is dropped without a word — hence the count is read back.
    """
    _require_writes()
    response = get_session().action(
        _SUBMIT_ACTION,
        {
            "placement": _SET_ITEMS,
            "productIds": [str(sku) for sku in skus],
            "content": {},
            "selectionUuid": str(uuid),
        },
    )
    said = _complaint(response)
    if said:
        msg = f"Ozon refused to change the selection's products: {said}"
        raise OzonError(msg)
    return _find(str(uuid))


def set_selection_public(uuid: str, *, public: bool) -> Selection:
    """Publish a selection to the account's public profile, or unpublish it.

    Ozon offers only a toggle, so the current state is read first and the toggle
    pressed only when it disagrees — pressing it blindly would publish exactly
    the selections that were already private. The state comes from the form
    rather than from the listed status, which says "На модерации" either way
    while a publication is under review.
    """
    _require_writes()
    current = get_selection(str(uuid))
    if current.public is public:
        return current
    response = get_session().action(_PUBLIC_ACTION, {"selectionUuid": str(uuid)})
    said = _complaint(response)
    if said:
        msg = f"Ozon refused to change the selection's visibility: {said}"
        raise OzonError(msg)
    return get_selection(str(uuid))


def delete_selection(uuid: str) -> WriteResult:
    """Delete a selection. Ozon's own words: "Восстановить её не получится"."""
    _require_writes()
    response = get_session().action(_DELETE_ACTION, {"selectionUuid": str(uuid)})
    said = _complaint(response)
    if said:
        return WriteResult(ok=False, detail=said)
    bar = response.get("notificationBar") if isinstance(response, dict) else None
    title = bar.get("title") if isinstance(bar, dict) else None
    return WriteResult(detail=str(title) if title else None)
