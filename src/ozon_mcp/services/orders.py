"""Order + archive (completed-orders) services."""

from __future__ import annotations

import re
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Final

from ozon_mcp.dependencies import get_session
from ozon_mcp.errors import OzonError, WritesDisabledError
from ozon_mcp.models.checkout import CancelReason, OrderCancelled, PaymentRequested
from ozon_mcp.parsing.common import find_all, walk, widget
from ozon_mcp.parsing.orders import order_numbers_from_link, parse_orders
from ozon_mcp.parsing.returns import parse_returns
from ozon_mcp.settings import get_settings
from ozon_mcp.utils.money import format_money, to_kopecks
from ozon_mcp.utils.serde import dumps, loads

if TYPE_CHECKING:
    from ozon_mcp.models.orders import Order, Return


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
        match = re.search(r"/my/orderlist\?[^\"\\ ]*archiveOrdersStart=\d+[^\"\\ ]*", dumps(data))
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
# The returns list is a container the page fetches after itself.
_RETURNS_PATH: Final = "/my/returns?layout_container=returns-list-desktop&layout_page_index={index}"
# The list starts at the second index: the first is the page itself.
_FIRST_RETURN_PAGE: Final = 2
_MAX_RETURN_PAGES: Final = 40
_ORDER_NUMBER_RE: Final = re.compile(r"\d{6,}-\d{3,}")
_CANCEL_MODAL_ACTION: Final = "selectCancelModalRms"
_CANCEL_ORDER_ACTION: Final = "v2/cancelOrderRms"
_MODAL_CONSTRUCTOR_ACTION: Final = "v2/openModalConstructorRms"
_REASONS_MODAL: Final = "/modal/selectCancelReasonRms"
# Ozon's own wording; the catch-all one is rejected without a comment.
_NEEDS_COMMENT_REASON: Final = "508"


def _cancel_postings_modal(order: str) -> str:
    response = get_session().action(f"{_CANCEL_MODAL_ACTION}?orderNumber={order}", {"orderNumber": order})
    link = ((response.get("action") or {}) or {}).get("link")
    if not link:
        msg = f"order {order} cannot be cancelled (Ozon offered no cancel form)"
        raise OzonError(msg)
    return str(link)


def _typed(params: dict[str, Any]) -> dict[str, Any]:
    """Restore the JSON types Ozon flattened into strings.

    An action's params arrive as text ("False", "1634"), but the reason step
    expects the state it is given to carry real booleans and numbers — handed
    the flat strings it answers with an empty page and the cancellation stalls
    with no error to explain it.
    """
    typed: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str) and value in {"True", "False"}:
            typed[key] = value == "True"
        elif isinstance(value, str) and value.isdigit():
            typed[key] = int(value)
        else:
            typed[key] = value
    return typed


def _postings(state: Any) -> list[tuple[str, str]]:
    """``(posting id, product title)`` for each cancellable line of the order."""
    lines: list[tuple[str, str]] = []
    for item in (state.get("items") if isinstance(state, dict) else None) or []:
        if not isinstance(item, dict) or item.get("type") != "monoposting":
            continue
        body = item.get("monoposting") or {}
        current = ((body.get("action") or {}).get("params") or {}).get("Current")
        if current:
            lines.append((str(current), str(body.get("subtitle") or "")))
    return lines


def _select_postings(order: str, modal: str, skus: list[str]) -> dict[str, Any]:
    """Tick only the lines holding ``skus``, and prove that is what got ticked.

    Ozon identifies a line by its own posting id, not by sku, and the modal
    names the product only as a truncated title. So the choice is made by title
    and then checked against the ItemIds Ozon reports back — cancelling the
    wrong item of an order is not something to leave to a string match.
    """
    from ozon_mcp.services.catalog import order_products  # ruff: ignore[import-outside-top-level] - avoids a cycle

    session = get_session()
    titles = {product.sku: (product.title or "") for product in order_products(order)}
    unknown = [sku for sku in skus if sku not in titles]
    if unknown:
        msg = f"order {order} does not contain {', '.join(unknown)}"
        raise OzonError(msg)

    state = widget(session.fetch(modal, backend="entrypoint"), "cancelPostingsRms") or {}
    lines = _postings(state)
    if not lines:
        msg = f"order {order} exposes no cancellable lines"
        raise OzonError(msg)

    wanted: list[str] = []
    for sku in skus:
        title = titles[sku]
        match = next((pid for pid, subtitle in lines if subtitle and title.startswith(subtitle[:20])), None)
        if match is None:
            msg = f"could not find the line for {sku} in order {order}"
            raise OzonError(msg)
        wanted.append(match)

    selected: dict[str, Any] = {}
    for posting in wanted:
        selected = session.post_page(modal, {"Current": posting}, backend="entrypoint")

    button = (widget(selected, "cancelPostingsRms") or {}).get("button") or {}
    action = button.get("action") or (button.get("common") or {}).get("action") or {}
    chosen = re.findall(r"\d{6,}", str((action.get("params") or {}).get("ItemIds") or ""))
    if set(chosen) != set(skus):
        msg = f"Ozon selected {chosen or 'nothing'} instead of {skus}; refusing to cancel"
        raise OzonError(msg)
    return selected


def _reasons_modal(order: str, skus: list[str] | None = None) -> tuple[str, dict[str, Any]]:
    """Reach the reasons step, whichever way this order gets there.

    Ozon takes two routes depending on the order's state. A confirmed order goes
    through a parcel picker first, and the reasons step is unlocked by its
    button. An order still awaiting payment has no parcels to pick, so the entry
    action lands on the reasons directly — its parameters then live in the
    widget's own ``state`` instead of a button.
    """
    session = get_session()
    entry = _cancel_postings_modal(order)

    if _REASONS_MODAL in entry:
        state = widget(session.fetch(entry, backend="entrypoint"), "selectCancelReason") or {}
        try:
            carried = loads(state.get("state") or "{}")
        except (ValueError, TypeError):
            carried = {}
        params = carried.get("Parameters")
        if not isinstance(params, dict):
            msg = f"order {order} exposes no cancellation parameters"
            raise OzonError(msg)
        return entry, params

    # Load the form before acting on it: Ozon builds the per-order form on that
    # GET, and posting into one it has not built answers with an empty widget.
    if skus:
        selected = _select_postings(order, entry, skus)
    else:
        session.fetch(entry, backend="entrypoint")
        selected = session.post_page(entry, {"SelectAll": "True", "selectedIds": "[]"}, backend="entrypoint")
    button = (widget(selected, "cancelPostingsRms") or {}).get("button") or {}
    action = button.get("action") or (button.get("common") or {}).get("action") or {}
    if not action.get("link"):
        msg = f"order {order} can no longer be cancelled (already delivered, or nothing left in it)"
        raise OzonError(msg)
    opened = session.action(str(action["link"]), action.get("params") or {})
    link = ((opened.get("data") or {}).get("action") or {}).get("link")
    if not link:
        msg = "Ozon did not return the cancellation reasons"
        raise OzonError(msg)
    return str(link), dict(action.get("params") or {})


def _order_exists(page: dict[str, Any]) -> bool:
    """Whether an order page is an order at all.

    Ozon answers a number it does not know with a perfectly valid page that has
    no order on it, so asking to pay one used to come back as "nothing left to
    pay" — indistinguishable from a settled order. The shipment block is what
    only a real order has.
    """
    return any(widget(page, name) for name in ("shipmentWidget", "orderDoneTotal", "orderDetailsHeader"))


def list_returns(limit: int = 100) -> list[Return]:
    """The buyer's returns, newest first.

    The returns page carries none of them: they arrive in a container it fetches
    after itself, a few at a time, and what the page itself holds is the returns
    FAQ. Reading the page instead reported its FAQ questions as returns, and on
    an account that had returns it reported nothing.
    """
    session = get_session()
    out: list[Return] = []
    seen: set[str] = set()
    # The container advertises no paginator of its own: the page simply asks for
    # the next index, three returns at a time, until one comes back empty. Going
    # by the cursor instead stopped at the first three of eighteen.
    for index in range(_FIRST_RETURN_PAGE, _FIRST_RETURN_PAGE + _MAX_RETURN_PAGES):
        data = session.fetch(_RETURNS_PATH.format(index=index), backend="entrypoint")
        fresh = [entry for entry in parse_returns(data) if entry.number not in seen]
        if not fresh:
            break
        seen.update(entry.number for entry in fresh if entry.number)
        out += fresh
        if len(out) >= limit:
            break
    return out[:limit]


def resolve_order(order: str) -> str:
    """The order number behind whatever the caller passed.

    ``list_orders`` hands out a ``detail_link``, and it is the natural thing to
    pass on — but only the products tool ever accepted one, so cancelling or
    paying from a listed order failed on the id it was just given. The number is
    encoded in that link, so it is decoded here instead of being demanded.
    """
    text = str(order).strip()
    if _ORDER_NUMBER_RE.fullmatch(text):
        return text
    number = next(iter(order_numbers_from_link(text)), None)
    if number:
        return number
    msg = (
        f"{order!r} is neither an order number nor a link that carries one; "
        "pass order_number or detail_link from list_orders()"
    )
    raise OzonError(msg)


def list_cancel_reasons(order: str) -> list[CancelReason]:
    """Reasons Ozon will accept for cancelling this order."""
    order = resolve_order(order)
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


def _searchable(node_source: Any) -> list[Any]:
    """Nodes to walk, parsing a whole page response when given one.

    A raw response keeps every widget as a JSON *string*, so walking it finds
    no actions at all — which reads as "Ozon offered nothing" while the button
    is right there.
    """
    if isinstance(node_source, dict) and "widgetStates" in node_source:
        states = [widget(node_source, key.split("-")[0]) for key in node_source["widgetStates"]]
        return [state for state in states if state is not None]
    return [node_source]


def _follow_action(node_source: Any, needle: str) -> dict[str, Any] | None:
    """The first action whose link mentions ``needle``, wherever it is hung."""
    for source in _searchable(node_source):
        found = _action_in(source, needle)
        if found is not None:
            return found
    return None


def _action_in(node_source: Any, needle: str) -> dict[str, Any] | None:
    for node in walk(node_source):
        for holder in (node, node.get("common") if isinstance(node.get("common"), dict) else {}):
            action = holder.get("action") if isinstance(holder, dict) else None
            if isinstance(action, dict) and needle in str(action.get("link") or ""):
                return action
    return None


def cancel_order(
    order: str,
    skus: list[str] | None = None,
    reason_id: str = "504",
    comment: str = "",
    return_to_cart: bool = True,
) -> OrderCancelled:
    """Cancel an order and, by default, put its items back in the cart.

    ``reason_id`` comes from list_cancel_reasons; the default is "changed my
    mind, will reorder", the neutral one. Reason "508" is rejected without a
    ``comment``.

    Cancelling is a six-step conversation and every step hands the next its
    parameters — including ids, like the internal OrderId, that appear nowhere
    else. So each step follows the action the previous response carried instead
    of rebuilding it: select the parcels, open the reasons, choose one, open the
    modal Ozon puts between the reason and the deed (it offers to change the
    address instead), and only then confirm.
    """
    _require_writes()
    order = resolve_order(order)
    if reason_id == _NEEDS_COMMENT_REASON and not comment.strip():
        msg = f"reason {reason_id} requires a comment"
        raise OzonError(msg)

    session = get_session()
    link, params = _reasons_modal(order, skus)
    state = {"IsCheckboxChecked": return_to_cart, "Parameters": _typed(params), "Comment": comment}
    chosen = session.post_page(
        link,
        {"ReasonId": reason_id, "state": dumps(state)},
        backend="entrypoint",
    )

    opener = _follow_action(widget(chosen, "selectCancelReason") or {}, _MODAL_CONSTRUCTOR_ACTION)
    if opener is None:
        texts = [text for text in find_all(chosen, "text") if isinstance(text, str) and text.strip()]
        return OrderCancelled(
            order_number=order,
            cancelled=False,
            reason_id=reason_id,
            detail=" | ".join(dict.fromkeys(texts))[:300] or "Ozon did not offer the next step",
        )
    opened = session.action(str(opener["link"]), opener.get("params") or {})
    modal_link = ((opened.get("data") or {}).get("action") or {}).get("link")
    if not modal_link:
        return OrderCancelled(
            order_number=order, cancelled=False, reason_id=reason_id, detail="Ozon did not open the confirmation"
        )

    confirmation = session.fetch(str(modal_link), backend="entrypoint")
    confirm = _follow_action(widget(confirmation, "modalConstructor") or confirmation, _CANCEL_ORDER_ACTION)
    if confirm is None:
        texts = [text for text in find_all(confirmation, "text") if isinstance(text, str) and text.strip()]
        return OrderCancelled(
            order_number=order,
            cancelled=False,
            reason_id=reason_id,
            detail=" | ".join(dict.fromkeys(texts))[:300] or "Ozon offered no way to confirm",
        )

    result = session.action(str(confirm["link"]), confirm.get("params") or {})
    ok = result.get("_httpStatus") == HTTPStatus.OK
    return OrderCancelled(
        order_number=order,
        cancelled=ok,
        reason_id=reason_id,
        skus=skus or [],
        returned_to_cart=return_to_cart and ok,
        detail=None if ok else f"Ozon replied {result.get('_httpStatus')}",
    )


# --- paying an order that was left unpaid --------------------------------
_PAY_ACTION: Final = "v2/changePaymentMethodAndPay"
_CREATE_PAYMENT_ACTION: Final = "v2/createPayment"
_BANK_HOST: Final = "finance.ozon.ru"


_SHORTFALL_RE: Final = re.compile(r"не хватает\s+([\d\s\u202f\u00a0,.]+₽)")


def _money(kopecks: str | None) -> str | None:
    """Ozon states amounts in kopecks on this action; people read roubles."""
    if not kopecks or not str(kopecks).isdigit():
        return None
    return format_money(int(kopecks))


def pay_order(order: str) -> PaymentRequested:
    """Ask Ozon to charge an order that is still awaiting payment.

    ``v2/createPayment`` is asked directly rather than hunted for on the order
    page: the page grows its pay button only some time after the order appears,
    so a freshly placed order would read as "nothing to pay". The page is still
    read, because it is where Ozon states the amount and — when the Ozon Card
    balance does not cover it — how much is missing.

    The charge finishes on Ozon's bank domain, which asks the account to sign in
    to the bank. That is the account owner's step, so the result spells out what
    remains: top up by ``shortfall`` if set, then complete at ``payment_url``.
    """
    _require_writes()
    order = resolve_order(order)
    session = get_session()
    page = session.fetch(f"/my/orderdetails/?order={order}")
    if not _order_exists(page):
        msg = f"there is no order {order} on this account — check the number against list_orders()"
        raise OzonError(msg)
    starter = _follow_action(page, _PAY_ACTION)
    params = (starter or {}).get("params") or {}
    amount = _money(params.get("totalPrice") or params.get("finalPrepayPrice"))

    if amount is None:
        amount = _amount_due(page)

    texts = [text for text in find_all(page, "text") if isinstance(text, str)]
    shortfall = next(
        (match.group(1).strip() for text in texts if (match := _SHORTFALL_RE.search(text))),
        None,
    )
    if shortfall is None:
        # Ozon only prints the gap once it has noticed it; the numbers are known
        # here either way, and a caller needs to hear the amount, not wait.
        shortfall = _gap(amount)

    created = session.action(_CREATE_PAYMENT_ACTION, {"orderNumber": order})
    url = _payment_url(created)
    if url is None and starter is not None:
        started = session.action(str(starter["link"]), params)
        following = (started.get("data") or {}).get("action") or {}
        if following.get("link"):
            url = _payment_url(session.action(str(following["link"]), following.get("params") or {}))

    if url is None:
        return PaymentRequested(
            order_number=order,
            amount_due=amount,
            shortfall=shortfall,
            detail="this order has nothing left to pay",
        )

    needs_bank = _BANK_HOST in url
    steps = []
    if shortfall:
        steps.append(f"top up the Ozon Card by {shortfall}")
    if needs_bank:
        steps.append(f"open {url} and sign in to Ozon Bank to complete the payment")
    return PaymentRequested(
        order_number=order,
        amount_due=amount,
        shortfall=shortfall,
        payment_url=url,
        needs_bank_passcode=needs_bank,
        next_step="; then ".join(steps) or "complete the payment at payment_url",
        detail=(
            f"the Ozon Card balance is short by {shortfall}"
            if shortfall
            else "the balance covers the order; only the bank sign-in is left"
        ),
    )


def _amount_due(page: dict[str, Any]) -> str | None:
    """The "К оплате" figure Ozon shows on the order itself."""
    total = widget(page, "orderDoneTotal") or {}
    block = total.get("total") if isinstance(total, dict) else None
    right = (block or {}).get("right") if isinstance(block, dict) else None
    for candidate in find_all(right or {}, "text"):
        if isinstance(candidate, str) and "₽" in candidate:
            return str(candidate).strip()
    return None


def _gap(amount: str | None) -> str | None:
    """What the Ozon Card balance is short of ``amount``, if anything."""
    from ozon_mcp.services.finance import get_finances  # ruff: ignore[import-outside-top-level] - avoids a cycle

    due = to_kopecks(amount)
    if due is None:
        return None
    balance = to_kopecks(get_finances().ozon_card_balance)
    if balance is None or balance >= due:
        return None
    return _money(str(due - balance))


def _payment_url(response: dict[str, Any]) -> str | None:
    data = response.get("data") or {}
    url = data.get("link") or ((data.get("action") or {}).get("link"))
    return str(url) if url else None
