"""Order + archive (completed-orders) services."""

from __future__ import annotations

import json
import re
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Final

from ozon_mcp.dependencies import get_session
from ozon_mcp.errors import OzonError, WritesDisabledError
from ozon_mcp.models.checkout import CancelReason, OrderCancelled
from ozon_mcp.parsing.common import find_all, walk, widget
from ozon_mcp.parsing.orders import parse_orders
from ozon_mcp.settings import get_settings

if TYPE_CHECKING:
    from ozon_mcp.models.orders import Order


def _require_writes() -> None:
    if not get_settings().enable_writes:
        raise WritesDisabledError


_MAX_ARCHIVE_PAGES = 200


def _archive_pages(limit: int, stop_before: str | None = None) -> list[Order]:
    """Completed-orders history (tab «Завершённые»), paginated via the archive
    "load more" cursor embedded in each response. Archive is newest→oldest, so
    ``stop_before`` (ISO date) ends pagination once a whole page is older.
    """
    session = get_session()
    orders: list[Order] = []
    seen: set[str] = set()
    data = session.fetch("/my/orderlist?selectedTab=archive")
    for _ in range(_MAX_ARCHIVE_PAGES):
        page = parse_orders(data)
        for order in page:
            if order.detail_link and order.detail_link not in seen:
                seen.add(order.detail_link)
                orders.append(order)
        if len(orders) >= limit or not page:
            break
        if stop_before:
            page_dates = [o.date for o in page if o.date]
            if page_dates and max(page_dates) < stop_before:
                break
        match = re.search(
            r"/my/orderlist\?[^\"\\ ]*archiveOrdersStart=\d+[^\"\\ ]*", json.dumps(data, ensure_ascii=False)
        )
        if not match:
            break
        following = match.group(0).replace("\\u0026", "&").replace("\\/", "/")
        data = session.fetch(following, backend="entrypoint")
    return orders[:limit]


def list_orders(
    scope: str = "active",
    limit: int = 100,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[Order]:
    """Orders, optionally narrowed to a date range.

    A range implies the archive (only completed orders carry dates) and lets
    pagination stop as soon as it walks past the window, which is what keeps
    "what did I buy in July" from reading the whole history.
    """
    if date_from or date_to:
        return orders_by_date(date_from or "0000-01-01", date_to or "9999-12-31", limit)
    orders: list[Order] = []
    if scope in {"active", "all"}:
        orders += parse_orders(get_session().fetch("/my/orderlist"))
    if scope in {"completed", "all"}:
        orders += _archive_pages(limit)
    return orders if scope == "active" else orders[:limit]


def orders_by_date(date_from: str, date_to: str, max_orders: int = 300) -> list[Order]:
    return [o for o in _archive_pages(max_orders, stop_before=date_from) if o.date and date_from <= o.date <= date_to]


# --- cancellation -----------------------------------------------------------
# Cancelling is a five-step conversation, each step handing the next its
# parameters. Rather than rebuilding those parameters (they include ids only the
# server knows, like OrderId), every step follows the action the previous
# response carried — which is what the site itself does.
_CANCEL_MODAL_ACTION: Final = "selectCancelModalRms"
_CANCEL_ORDER_ACTION: Final = "v2/cancelOrderRms"
# Ozon's own wording; the catch-all one is rejected without a comment.
_NEEDS_COMMENT_REASON: Final = "508"


def _cancel_postings_modal(order: str) -> str:
    response = get_session().action(f"{_CANCEL_MODAL_ACTION}?orderNumber={order}", {"orderNumber": order})
    link = ((response.get("action") or {}) or {}).get("link")
    if not link:
        msg = f"order {order} cannot be cancelled (Ozon offered no cancel form)"
        raise OzonError(msg)
    return str(link)


def _reasons_modal(order: str) -> tuple[str, dict[str, Any]]:
    """Select every parcel, then open the reasons step it unlocks."""
    session = get_session()
    modal = _cancel_postings_modal(order)
    # The modal is an entrypoint page: posting to composer answers with a page
    # that has selected nothing, which reads as "nothing cancellable".
    selected = session.post_page(modal, {"SelectAll": "True", "selectedIds": "[]"}, backend="entrypoint")
    button = (widget(selected, "cancelPostingsRms") or {}).get("button") or {}
    action = button.get("action") or (button.get("common") or {}).get("action") or {}
    if not action.get("link"):
        msg = f"order {order} has nothing cancellable left"
        raise OzonError(msg)
    opened = session.action(str(action["link"]), action.get("params") or {})
    link = ((opened.get("data") or {}).get("action") or {}).get("link")
    if not link:
        msg = "Ozon did not return the cancellation reasons"
        raise OzonError(msg)
    return str(link), dict(action.get("params") or {})


def list_cancel_reasons(order: str) -> list[CancelReason]:
    """Reasons Ozon will accept for cancelling this order."""
    link, _ = _reasons_modal(order)
    state = widget(get_session().fetch(link, backend="entrypoint"), "selectCancelReason") or {}
    reasons: list[CancelReason] = []
    for node in walk(state):
        action = node.get("common", {}).get("action") if isinstance(node.get("common"), dict) else None
        reason_id = ((action or {}).get("params") or {}).get("ReasonId")
        if not reason_id:
            continue
        title = ((node.get("centerBlock") or {}).get("title") or {}).get("text")
        reasons.append(
            CancelReason(
                reason_id=str(reason_id),
                label=title,
                needs_comment=str(reason_id) == _NEEDS_COMMENT_REASON,
            )
        )
    return reasons


def cancel_order(
    order: str,
    reason_id: str = "504",
    comment: str = "",
    return_to_cart: bool = True,
) -> OrderCancelled:
    """Cancel an order and, by default, put its items back in the cart.

    ``reason_id`` comes from list_cancel_reasons; the default is "changed my
    mind, will reorder", which is the neutral one. Reason "508" is rejected
    without a ``comment``.

    Ozon inserts a retention screen between the reason and the cancellation, so
    the confirming action is taken from the response rather than assumed — that
    screen is why choosing a reason alone leaves the order alive.

    **Known gap:** the reason step currently answers with an empty shell rather
    than that screen, so this returns ``cancelled=False`` with what Ozon said
    instead of finishing. The final call is ``v2/cancelOrderRms`` and needs the
    numeric ``OrderId``, which none of the reachable payloads expose. Cancelling
    through the site works; automating it does not yet.
    """
    _require_writes()
    if reason_id == _NEEDS_COMMENT_REASON and not comment.strip():
        msg = f"reason {reason_id} requires a comment"
        raise OzonError(msg)

    session = get_session()
    link, params = _reasons_modal(order)
    state_payload = {
        "IsCheckboxChecked": return_to_cart,
        "Parameters": params,
        "Comment": comment,
    }
    chosen = session.post_page(
        link,
        {"ReasonId": reason_id, "state": json.dumps(state_payload, ensure_ascii=False)},
        backend="entrypoint",
    )

    confirm = next(
        (
            node["action"]
            for node in walk(chosen)
            if isinstance(node.get("action"), dict) and _CANCEL_ORDER_ACTION in str(node["action"].get("link") or "")
        ),
        None,
    )
    if confirm is None:
        # No confirming action means Ozon is still asking something (its
        # retention offer), so report that instead of pretending success.
        texts = [text for text in find_all(chosen, "text") if isinstance(text, str) and text.strip()]
        return OrderCancelled(
            order_number=order,
            cancelled=False,
            reason_id=reason_id,
            detail=" | ".join(dict.fromkeys(texts))[:300] or "Ozon did not offer the confirming step",
        )

    payload = dict(confirm.get("params") or {})
    payload["Comment"] = comment
    payload["IsCheckboxChecked"] = str(return_to_cart)
    result = session.action(str(confirm["link"]), payload)
    ok = result.get("_httpStatus") == HTTPStatus.OK
    return OrderCancelled(
        order_number=order,
        cancelled=ok,
        reason_id=reason_id,
        returned_to_cart=return_to_cart and ok,
        detail=None if ok else f"Ozon replied {result.get('_httpStatus')}",
    )
