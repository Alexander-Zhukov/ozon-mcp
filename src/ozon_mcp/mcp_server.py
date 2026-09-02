"""The MCP server itself: the instance every tool registers on.

Kept apart from the tools so that a tool module can import the server without
the server having to know about the tools — the tools are attached in
``main``, which is the only place that knows the whole set.

``instructions`` is what a client is handed on connect, and it is the only
documentation an agent gets before it starts calling things.
"""

from typing import Final

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from ozon_mcp.settings import get_settings

INSTRUCTIONS: Final = """Read-write access to one ozon.ru buyer account: orders, purchases, returns, cart,
favorites, collections, product cards, catalog search, checkout, Ozon Card balance and points.
Everything acts on the signed-in account of a real person, and money is real.

Start with session_status(). It answers three things you cannot guess: whether the session is
alive, whether you may change anything (writes_enabled) and whether you may place an order
(orders_enabled). Those two are the operator's settings — no tool can change them, so plan
around them instead of discovering them halfway through.

Buying, in order — each step is a precondition for the next:
  1. find the product: search() -> product_details() and take the SKU of the exact variant
     (apparel: the size's own SKU, not the base one)
  2. set_cart_quantity(sku, n)
  3. select_cart_items([sku, ...], mode="only") — the ticks ARE the order's contents, and
     get_checkout() sees nothing until something is ticked
  4. get_checkout() — read it before deciding anything: it lists the payment methods, the
     pickup points, the pay-on-delivery switch and the money
  5. configure_checkout(...) with values taken from that answer
  6. show the user totals.order_total, then place_order(confirm_total=<that figure>)
  7. if payment is still pending: pay_order(order_number)
Undo: cancel_order(order_number), optionally skus=[...] for single lines.

Two kinds of lists, and they are not interchangeable: wishlists (вишлисты) via
get_lists / create_list / set_list_membership, and «Подборки» via list_selections /
selection_products / create_selection / add_to_selection / remove_from_selection —
curated, publishable, addressed by uuid, and filled only from favorites. A selection's products
are a separate read: the list states a count only. Publishing a selection is outward-facing — it
appears on the account owner's public profile, so ask first.

Two figures, never interchangeable: totals.total is what Ozon charges today, totals.order_total
is what the order costs. On a pay-on-delivery order today's charge is 0 ₽ — quote order_total to
the user, or you will tell them a 6 691 ₽ order is free. pay_after_receipt.scope says whether
deferral covers the whole order ("full"), part of it ("partial", and then pay_now_items /
pay_on_receipt_items name which lines fall on which side) or nothing ("none").

list_orders() states no order total, because Ozon states none. A row carries amount_due_at_pickup
(«К оплате при получении») and, per item, that item's price and paid true/false. An item's price
is not the order's; paid null means unknown, not unpaid. "active" leaves out the received and
cancelled orders Ozon shows among the current ones; state says which is which.

A product card states three prices and only one is charged: price is «С банками» — what this
account pays — beside price_regular («С другими банками») and price_old. Rank lots on the first;
search(sort="cheap") and find_cheaper already do. In search, limit is depth, not page size —
pages are walked until it is met, and the cheapest lot is regularly not on the first one. Ozon's
text search is literal: a lot whose own title omits the brand does not come back for a query that
includes it, so search the model rather than brand-plus-model, and confirm what a lot is with
product_details() — a tile's title is the seller's wording and may name no model at all. A query
Ozon finds nothing exact for returns nothing rather than the "you might also like" it fills the
page with. find_cheaper adds Ozon's own «Есть дешевле или быстрее» offers for that product.

A rating and a review count are Ozon's own numbers: product_details() carries rating,
reviews_count and questions_count, and get_reviews() adds the breakdown per star plus as many
reviews as `limit` asks for. count is the product's total and fetched is what came back — quoting
the second as the first turns 155 847 reviews into 30. There is no filter by star, so the
complaints are reached with sort="worst" and depth; each review keeps «Достоинства» and
«Недостатки» apart and names the variant it is about, because a card's reviews cover its sizes
and colours.

list_orders() dates are status dates — when an order was received or cancelled, the only dates the
archive prints — and a range is walked down to, so the cost is the depth, not the width.

«Купленные товары» (purchases) is a list of what was ordered, not of what arrived: it includes
items refused at the pickup point, states no status and prices them at today's catalogue price.
bought_items() answers "did I actually get this" by matching it against the orders, where the
outcome lives per parcel — one order holds «Получен» and «Отменён» at once. Each order opened is
a request, so bought_items is bounded and reports its own reach: scanned_orders,
scanned_back_to, complete, unresolved (never seen) and provisional (seen only as cancelled — an
older order may have been received, so it is not an answer yet). Keep looking by asking about the
leftovers, not by raising the bound:
  bought_items(skus=<unresolved + provisional>, scan_before=<scanned_back_to>)
repeated until complete, merging by sku and preferring received. Never report unresolved as "not
bought" — it means nobody looked that far back. Budget: a first call with a query ~40-50 s, each
continuation of 150 orders ~30 s.

A failure never arrives as an empty result: a 502, a timeout or a rate limit raises, because "no
orders" and "Ozon did not answer" are different answers. Every error carries a code before its
sentence — [upstream_unavailable], [rate_limited], [session_expired], [writes_disabled],
[orders_disabled], [total_mismatch]. Branch on the code; relay the sentence, which is written for
a person. A signed-out session raises everywhere rather than answering with an empty account:
recover with start_login(login) and submit_login_code(code), which needs a code only the account
owner receives — so ask, never guess.

Paying by card finishes on Ozon's bank domain, which asks the account to sign in to the bank —
this server holds no banking credentials. pay_order drives it to that point and reports what is
left: the amount, how much to top the card up by, and the page to finish at. Pay-on-delivery
avoids the whole thing.

Prices, dates and addresses are returned as Ozon renders them, in Russian and in roubles. Pass
identifiers back exactly as received."""


def _transport_security() -> TransportSecuritySettings:
    """Whether to check the Host header, and against what.

    The check is an exact match, so it can only be enabled by naming the hosts:
    with none named it stays off, or every client using the address it was given
    would be answered 421 by a server that is working correctly.
    """
    allowed = get_settings().allowed_hosts
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(allowed),
        allowed_hosts=allowed,
    )


mcp: Final = FastMCP("ozon", instructions=INSTRUCTIONS, transport_security=_transport_security())
