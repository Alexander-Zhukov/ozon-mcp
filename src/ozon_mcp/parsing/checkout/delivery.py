"""Where the order goes: destinations, pickup points, shipments.

A destination is read from the cell Ozon draws with a location pin, and the
recipient from the row that edits exactly that — the two look alike otherwise.
Shipments carry the split keys every per-shipment call needs.
"""

import re
from typing import Any, Final

from ozon_mcp.models.checkout import Delivery, PickupPoint, Shipment, ShipmentItem
from ozon_mcp.parsing.checkout.atoms import BR_RE, action_link, plain, text
from ozon_mcp.parsing.common import walk, widgets_all
from ozon_mcp.utils.money import format_money, to_kopecks
from ozon_mcp.utils.serde import dumps

_RECIPIENT_ACTION: Final = "editAddressAndRecipient"
# The destination cell is the one drawn with a location pin; the recipient cell
# looks the same but carries a profile icon.


_ADDRESS_ICON: Final = "ic_m_location_pin_filled"


_ADDRESS_BOOK: Final = "miniaddressbook"
# How Ozon names instalments among the payment methods it declares.


_SPLIT_KEY_RE: Final = re.compile(r"split_key=([A-Za-z0-9\-]+)")


def _point_number(entry: dict[str, Any]) -> str | None:
    """The pickup point's public number.

    ``numberPVZ`` holds it twice: rendered as «№ 144-94-60» and plain in the
    copy-to-clipboard action. The plain one is what a person types back, so it
    is preferred; only a pickup point has this block at all, which is what tells
    a point apart from a courier address.
    """
    block = entry.get("numberPVZ") if isinstance(entry.get("numberPVZ"), dict) else None
    if block is None:
        return None
    for node in walk(block):
        action = node.get("action")
        if isinstance(action, dict) and action.get("id") == "copyText":
            value = (action.get("params") or {}).get("clipboardText")
            if value:
                return str(value)
    return plain(text(block.get("number")))


def _apply_link(entry: dict[str, Any]) -> str | None:
    for node in walk(entry):
        link = action_link(node)
        if "apply_address_split=" in link:
            return link
    return None


def parse_pickup_points(state: Any) -> list[PickupPoint]:
    """Saved addresses from the address-book modal.

    Each entry carries its own apply link; entries without one are points Ozon
    will not ship this cart to, so they are returned as unavailable rather than
    hidden — the caller can explain why.
    """
    points: list[PickupPoint] = []
    for entry in (state.get("addresses") if isinstance(state, dict) else None) or []:
        if not isinstance(entry, dict):
            continue
        # Every entry states its own lines in order: the address first, then
        # either the storage term (a pickup point) or the flat/floor detail and
        # the recipient (a courier address). Reading them positionally is what
        # avoids guessing an address by "the first text longer than 12 chars".
        lines = [line for line in (plain(text(element)) for element in entry.get("elements") or []) if line]
        number = _point_number(entry)
        apply_link = _apply_link(entry)
        rest = lines[1:]
        notes = [note for note in (plain(text(element)) for element in entry.get("bottomElements") or []) if note]
        points.append(
            PickupPoint(
                address_book_id=entry.get("addressBookId"),
                title=plain(text(entry.get("title"))),
                # A courier address spreads over its lines; a point is one line
                # plus how long it keeps the parcel.
                address=", ".join(lines if number is None else lines[:1]) or None,
                number=number,
                storage=rest[0] if number is not None and rest else None,
                selected=bool(entry.get("isSelected")),
                available=bool(entry.get("isEnabled")) and apply_link is not None,
                note=" ".join(notes) or None,
            )
        )
    return points


def pickup_apply_link(state: Any, address_book_id: str) -> str | None:
    """The link that switches the order to ``address_book_id``."""
    for entry in (state.get("addresses") if isinstance(state, dict) else None) or []:
        if isinstance(entry, dict) and entry.get("addressBookId") == address_book_id:
            return _apply_link(entry)
    return None


def _address_cell(state: Any) -> dict[str, Any]:
    """The cell showing where the order goes, found by the pin it is drawn with.

    The recipient sits in a cell of the same shape right below it, so the two
    are told apart by their icons rather than by what their text looks like.
    """
    for node in walk(state):
        icon = dumps(node.get("leftBlock") or {})
        if _ADDRESS_ICON in icon and isinstance(node.get("centerBlock"), dict):
            return node
    return {}


def parse_delivery(state: Any) -> Delivery:
    """Where this part of the order goes, and how.

    The mode is a tag list, and the selected tag is the mode — no guessing from
    the wording. The address cell states the point and, after a ``<br>``, how
    long it keeps a parcel: Ozon writes them in that order, so they are taken by
    position. Deciding which half was which by looking for "хранение" broke on
    a courier address, which has no storage term but does have a flat and a
    floor.
    """
    mode, change_link = None, None
    for node in walk(state):
        link = action_link(node)
        if _ADDRESS_BOOK in link:
            change_link = change_link or link
            if node.get("isSelected"):
                mode = text(node)
    center: dict[str, Any] = _address_cell(state).get("centerBlock") or {}
    label = plain(text(center.get("title")))
    pieces = [plain(piece) for piece in BR_RE.split(text(center.get("subtitle")) or "")]
    lines = [piece for piece in pieces if piece]
    return Delivery(
        mode=mode,
        address=", ".join(filter(None, (label, lines[0] if lines else None))) or None,
        storage=" ".join(lines[1:]) or None,
        recipient=_recipient(state),
        change_link=change_link,
    )


def _recipient(state: Any) -> str | None:
    """Who the order is addressed to, from the row that edits exactly that.

    Ozon gives the row its own action (``/modal/editAddressAndRecipient``), so
    the name is read from there instead of being recognised by shape — the old
    "two capitalised words then digits" pattern missed a single-word name, a
    double-barrelled surname and anything not in Cyrillic.
    """
    for node in walk(state):
        if _RECIPIENT_ACTION not in action_link(node):
            continue
        for inner in walk(node):
            center = inner.get("centerBlock")
            title = text((center or {}).get("title")) if isinstance(center, dict) else None
            if title:
                return plain(title)
    return None


def parse_deliveries(data: dict[str, Any]) -> list[Delivery]:
    """One entry per destination widget, each tagged with the shipments it covers."""
    deliveries: list[Delivery] = []
    for state in widgets_all(data, "rfbsAddressInfo"):
        delivery = parse_delivery(state)
        keys: list[str] = []
        for node in walk(state):
            for key in _SPLIT_KEY_RE.findall(action_link(node)):
                if key not in keys:
                    keys.append(key)
        delivery.split_keys = keys
        deliveries.append(delivery)
    return deliveries


def parse_shipments(data: dict[str, Any]) -> list[Shipment]:
    """The order's shipments, each with the id Ozon addresses it by.

    Read from each ``rfbsSplit`` widget's own fields rather than by scanning the
    page's text: the id is what every per-shipment call needs, and text order is
    not a reliable way to pair a date with a shipment.
    """
    shipments: list[Shipment] = []
    for state in widgets_all(data, "rfbsSplit"):
        if not isinstance(state, dict) or not state.get("id"):
            continue
        header = state.get("header") if isinstance(state.get("header"), dict) else {}
        shipments.append(
            Shipment(
                split_key=str(state["id"]),
                delivery=plain(text(header.get("text"))),
                summary=plain(text(state.get("subHeader"))),
            )
        )
    return sorted(shipments, key=lambda shipment: shipment.split_key or "")


def shipment_detail_link(data: dict[str, Any], split_key: str) -> str | None:
    """The link to a shipment's contents, as that shipment declares it.

    It carries the currently chosen address, so it is taken from the payload
    instead of being assembled from the split key alone.
    """
    for state in widgets_all(data, "rfbsSplit"):
        if isinstance(state, dict) and str(state.get("id")) == split_key:
            action = state.get("action") if isinstance(state.get("action"), dict) else {}
            link = action.get("link")
            return str(link) if link else None
    return None


def detail_items(state: Any) -> list[ShipmentItem]:
    """Lines of one ``splitDetailWebV2`` widget.

    ``vertical.splits`` groups the lines by seller; each line states its title
    and variant as two text atoms of ``mainColumn``, its price separately, and
    its quantity in ``sideColumn``.
    """
    items: list[ShipmentItem] = []
    vertical = state.get("vertical") if isinstance(state, dict) else None
    for group in (vertical or {}).get("splits") or []:
        if not isinstance(group, dict):
            continue
        seller = plain(text(group.get("title")))
        for entry in group.get("items") or []:
            if not isinstance(entry, dict):
                continue
            labels = [plain(text(atom.get("textAtom"))) for atom in entry.get("mainColumn") or []]
            labels = [label for label in labels if label]
            price = entry.get("price") if isinstance(entry.get("price"), dict) else {}
            quantity = next((plain(text(cell)) for cell in entry.get("sideColumn") or []), None)
            items.append(
                ShipmentItem(
                    title=labels[0] if labels else None,
                    variant=labels[1] if len(labels) > 1 else None,
                    price=plain(text(price.get("price")) or price.get("price")),
                    quantity=quantity,
                    seller=seller,
                )
            )
    return items


def parse_shipment_items(data: dict[str, Any]) -> list[ShipmentItem]:
    """Contents of one shipment, from its detail modal."""
    items: list[ShipmentItem] = []
    for state in widgets_all(data, "splitDetailWebV2"):
        items += detail_items(state)
    return items


def shipment_total(items: list[ShipmentItem]) -> str | None:
    """What a shipment costs, summed from its lines."""
    amounts = [to_kopecks(item.price) for item in items]
    known = [amount for amount in amounts if amount is not None]
    return format_money(sum(known)) if known and len(known) == len(amounts) else None
