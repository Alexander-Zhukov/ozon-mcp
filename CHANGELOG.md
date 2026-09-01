# Changelog

Notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow
[SemVer](https://semver.org/).

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
