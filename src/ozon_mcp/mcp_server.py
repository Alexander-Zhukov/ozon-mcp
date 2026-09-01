"""The MCP server itself: the instance every tool registers on.

Kept apart from the tools so that a tool module can import the server without
the server having to know about the tools — the tools are attached in
``main``, which is the only place that knows the whole set.

``instructions`` is what a client is handed on connect, and it is the only
documentation an agent gets before it starts calling things.
"""

from typing import Final

from mcp.server.fastmcp import FastMCP

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
get_lists / create_list / set_list_membership, and «Подборки» via
list_selections / create_selection / set_selection_items — curated, publishable,
addressed by uuid, and filled only from favorites. Publishing a selection is
outward-facing: it appears on the account owner's public profile, so ask first.

Two figures, never interchangeable: totals.total is what Ozon charges today, totals.order_total
is what the order costs. On a pay-on-delivery order today's charge is 0 ₽ — quote order_total to
the user, or you will tell them a 6 691 ₽ order is free. pay_after_receipt.scope says whether
deferral covers the whole order ("full"), part of it ("partial", and then pay_now_items /
pay_on_receipt_items name which lines fall on which side) or nothing ("none").

When a tool raises, the message says what to do next; it is written to be relayed. A signed-out
session raises everywhere rather than answering with an empty account: recover with
start_login(login) and submit_login_code(code), which needs a code only the account owner
receives — so ask, never guess.

Prices, dates and addresses are returned as Ozon renders them, in Russian and in roubles. Pass
identifiers back exactly as received."""

mcp: Final = FastMCP("ozon", instructions=INSTRUCTIONS)
