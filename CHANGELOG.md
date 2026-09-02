# Changelog

Notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow
[SemVer](https://semver.org/).

## [1.3.0] - 2026-09-02

### Fixed

- **A date window deep in the archive answered "nothing".** The archive is a
  newest-first cursor, so a window has to be walked down to — but the limit
  counted every row scanned, not the rows inside the window, so asking for July
  2024 with a limit of 500 stopped somewhere in 2025 and reported an empty month
  that in fact held eleven orders. The limit now counts matches, and paging ends
  once a page is wholly older than the window.

### Changed

- `order_products` reports each item's parcel: `shipment_status`
  («Получен» / «Отменён»), `received` and the order number. An order is delivered
  in parcels with separate fates — refusing something at the pickup point cancels
  its parcel while the rest of the order is received — and flattening them lost
  that, so a sku appearing in two parcels is now kept once per parcel.
- `purchases` returns `Purchase` rather than `Tile`, and its docstring says what
  the list is: everything ever **ordered**, refusals included, with no status and
  a catalogue price rather than the price paid.

### Added

- `purchases(with_status=true)` fills in each item's outcome from the orders —
  `order_number`, `order_status`, `received` — with `scan_orders` bounding how
  deep it looks. `received` null means "not found among the orders scanned".
  Measured on the account it was built against: 870 orders reaching back to 2020,
  0.16 s each, so a full sweep is about two and a half minutes; Ozon has no
  search over orders, which is why the purchases list is used as the index.

## [1.2.1] - 2026-09-02

### Fixed

- Search phrases were escaped twice, so any query with non-ASCII characters
  reached Ozon as nonsense — "тунец" as `%25D1%2582…` — and Ozon answered it with
  whatever it liked: car accessories, for canned tuna. 1.2.0 added the escaping
  in the service without noticing that the transport escapes the path as well.
  The transport now leaves `%` alone, and the phrase is escaped once, at the one
  place that knows it is a value.
- `get_search_filters` and the purchase-history search did not escape the phrase
  at all: one holding `&` detached into a parameter of its own.

## [1.2.0] - 2026-09-02

### Fixed

- **A widget name is now matched whole.** Names were matched by prefix, so asking
  a product card for `webPrice` could return `webPriceDecreasedCompact` instead —
  whichever Ozon served first. The same card therefore answered with its price or
  with «Стало дешевле» at random, which is how `find_cheaper` came to report
  "nothing is cheaper" for a product it had failed to price.
- **`search` walks the results.** It read one page and stopped, and a page is not
  the results: some queries put no tiles in the page at all and serve them only
  through its paginator, which was never followed because that widget is named
  `infiniteVirtualPaginator`. `limit` is now depth, and pages are walked to meet
  it.
- **A query with no exact match no longer answers with unrelated products.** Ozon
  marks that continuation `non_found=1` and fills it with "you might also like";
  those pages are dropped, so such a query returns nothing instead of ranking car
  cloths as the cheapest mouse.
- **`find_cheaper` raises when it cannot read the base price**, instead of
  answering with an empty list that reads as "nothing is cheaper".
- The card's sku came back as «Артикул: 3662719065», label and all, breaking every
  URL built from it.
- `start_login` reported "a code was sent" without checking that Ozon had moved on
  to asking for one. An address Ozon does not know, or a form that wanted a phone,
  therefore became "waiting for a code that never arrives" — now it says what the
  form said.
- `entrypoint.sh` clears a stale X lock and fails loudly if the display does not
  come up. A container that was stopped and started rather than recreated kept its
  `/tmp`, Xvfb refused the display, and the server ran with /metrics answering and
  every tool failing.

### Changed

- Prices are read from the fields Ozon names: `price` is «С банками» — what is
  actually charged — with `price_regular` and `price_old` beside it, on both cards
  and tiles. `ProductCard.price_list` is gone; it was the first money-looking
  strings in the widget, in payload order.
- `search(sort="cheap"/"expensive")` ranks on the payable price rather than
  trusting Ozon's own order, which goes by a different figure.
- `find_cheaper` merges two sources into one ranking: Ozon's «Есть дешевле или
  быстрее» offers for this exact product, and a price-sorted search by the card's
  title, filtered to lots whose titles actually resemble it. Offers carry
  `seller` and `delivery`.

### Added

- `ProductCard.available`, and `cheaper_offers` / `cheaper_from` — Ozon's own count
  of other offers and the lowest price among them.

## [1.1.1] - 2026-09-01

### Fixed

- The checkout could describe an order the caller had not composed. Ozon's
  checkout is a snapshot of the cart's ticks taken when checkout is entered, and
  only an entry replaces it — the cart reported one item and 649 ₽ while the
  checkout kept two and 768 ₽, in the site's own browser as well. `get_checkout`
  and `place_order` now enter checkout the way the cart's «Перейти к оформлению»
  button does, which keeps the options already chosen. The `initCheckoutState`
  action this used to rely on answers 503 and never rebuilt anything.

## [1.1.0] - 2026-09-01

### Added

- **A selection's products can be read**: `selection_products` lists what a
  «Подборка» holds. Neither the list nor the edit form carries them — the list
  states a count, the form only the text fields — so they come from the
  selection page's own container, named explicitly because the page's paginator
  points at recommendations instead.
- `add_to_selection` / `remove_from_selection`. Ozon has no "add": the form
  always submits the whole list, so sending only the additions replaced the
  selection with them. These read the current products first.
  `set_selection_items` stays as the way to set the whole list at once.
- `create_selection` now returns the selection's link.

### Fixed

- `delete_selection` reported a refusal as a success. Ozon answers one with
  HTTP 200, empty error fields and the reason in a notification bar, so the
  outcome is now decided by re-reading the list — and the selection has to exist
  first, because a uuid that was never there is absent from the list too.

## [1.0.0] - 2026-09-01

First stable release. 39 tools over one ozon.ru buyer account.

### Reading

- **Orders** — active, archive or both, each with its order number, status,
  state, pickup point, slot and ETA; optionally within a date range. Money as
  Ozon states it: «К оплате при получении» per delivery group, price and payment
  state per item, no invented order total. Items of one order with sku, title,
  price paid, chosen variant and seller.
- **Purchase history** — the whole list, or Ozon's own server-side search over it.
- **Returns** — number, application date, status, amount and the products going
  back.
- **Catalog** — storefront search by text and/or category with sort and facet
  filters; product cards with variants, characteristics and gallery; descriptions;
  reviews; delivery estimates; "find the same thing cheaper".
- **Cart** — items, quantities, ticks, Ozon's group headings, and the size Ozon
  itself declares.
- **Favorites, wishlists and «Подборки»** — contents, sizes, membership,
  visibility.
- **Money** — Ozon Card balance, points by type, burning points, per-store seller
  bonuses, and a price watch over favorites.

### Changing (behind `OZON_ENABLE_WRITES`)

- Cart quantities and the ticks that decide what an order contains.
- Favorites; wishlists created, filled and deleted; selections created, filled,
  renamed, published and deleted.
- Order cancellation, whole or item by item, returning the items to the cart.

### Ordering (behind `OZON_ENABLE_ORDERS`)

- Forming a checkout from the ticked cart items, reading everything it offers —
  payment methods, pay-on-delivery with its scope, destinations, pickup points,
  shipments, points, totals — and setting any of it in one call.
- Placing the order against a total the caller confirms, and reporting what a
  card payment still needs.

### Operational

- One browser bootstrap per session, then direct HTTP with Chrome's TLS
  fingerprint; no tool renders a page.
- Persistent Chromium profile as the session's home, backed up and restored
  around a sign-out; interactive recovery by one-time code.
- Retries with a cap and jitter, `Retry-After` honoured, upstream failures raised
  rather than returned as empty results.
- Errors carry a machine-readable code beside a sentence written to be relayed.
- Prometheus metrics at `/metrics`; `stdio` and `sse` transports.
