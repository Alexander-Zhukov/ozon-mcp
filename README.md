***English** · [Русский](README.ru.md)*

# Ozon MCP

An [MCP](https://modelcontextprotocol.io/) server for one **ozon.ru buyer
account**. It reads orders, purchases, returns, the cart, favorites, wishlists,
«Подборки», product cards, catalog search, the Ozon Card balance and points —
and, when explicitly allowed, changes the cart and the lists and runs an order:
forming a checkout, placing it, paying, cancelling it item by item.

None of this has a public API. The server talks to the same internal
`composer-api` / `entrypoint-api` endpoints the site's own frontend uses, under
your authenticated session.

## Requirements

- **A Russian IP.** Ozon blocks datacenter and VPN egress.
- **A real Chromium.** Headless is detected; the image runs it under Xvfb.
- **One interactive login**, performed once against the profile directory.
- `--shm-size=1g`. Chromium crashes on Docker's default 64 MB.

## How it works

The Variti antibot blocks non-browser clients, but a browser only has to pass
the challenge once. A real Chromium starts, passes it, and hands over its
cookies and the exact client-hint header set; from then on every read and write
is a direct HTTP call through [`curl_cffi`](https://github.com/lexiforest/curl_cffi)
with Chrome's TLS fingerprint. No tool renders a page, which is why a call takes
about 0.2 s instead of 15. The browser stays only to own the profile, refresh
the session, and serve as the fallback for one reading — the delivery estimate.

The session lives in a **persistent Chromium profile**, not a cookie snapshot.
OzonID, the auth realm guarding checkout, keeps its state outside cookies and
localStorage, so a Playwright `storage_state` snapshot silently loses it and
checkout falls back to a login prompt. A profile directory keeps everything, so
one login stays valid and the server runs unattended.

Playwright's sync API cannot run inside a live event loop, and its objects
belong to the thread that created them, so tool calls are dispatched to a single
worker thread. They are therefore serialised, and a slow one — a bootstrap, a
login — makes the others wait.

## Tools

**Orders and returns**

| Tool | |
|---|---|
| `list_orders` | Orders (active / archive / all), each with its `order_number`, status, state, pickup point, slot, what is owed on collection and per-item payment state; optionally within an ISO date range |
| `order_products` | Items of one order: sku, title, price paid, variant, seller |
| `purchases` | Everything ever bought, as product tiles; with a query, Ozon's own search over the history |
| `list_returns` | Returns: number, date, status, amount, the products going back |

**Catalog**

| Tool | |
|---|---|
| `search` | Storefront search by text and/or category slug, with sort and facet filters |
| `get_search_filters` | Facets available for a query, and the values `search` takes |
| `product_details` | Card: price, variants (each with its own sku), characteristics, photos; description and reviews on request |
| `get_reviews` | Reviews with score, text, dates, photos |
| `get_description` | Description text plus the images embedded in it |
| `delivery_estimate` | When a product would arrive, to which address, from which warehouse |
| `find_cheaper` | The same or a similar product below the current price |

**Cart**

| Tool | |
|---|---|
| `get_cart` | The whole cart: items, quantities, ticks, group headings, and the size Ozon declares |
| `set_cart_quantity` | Set the quantity; 0 removes |
| `select_cart_items` | Tick what makes up the order — `only` / `add` / `remove` / `all` / `none` |

**Favorites and wishlists**

| Tool | |
|---|---|
| `list_favorites` | Favorites as product tiles |
| `set_favorite` | Add or remove |
| `get_lists` | Wishlists with their ids and sizes; with a sku, whether each holds it |
| `create_list` / `delete_list` | Make a wishlist, or delete one |
| `set_list_membership` | Put a product in a wishlist or take it out |
| `check_favorite_price_drops` | Price changes since the previous call |

**«Подборки»**

| Tool | |
|---|---|
| `list_selections` | Selections with size, status, ids and the share link |
| `get_selection` | One selection in full, including description and visibility |
| `selection_products` | What it holds: sku, title, price, card link |
| `create_selection` | Create one around a product; private by default |
| `add_to_selection` | Add products, keeping the ones already in it |
| `remove_from_selection` | Take products out, keeping the rest |
| `set_selection_items` | Replace the whole list of products |
| `edit_selection` | Rename it, replace its description |
| `set_selection_public` | Publish to the public profile, or unpublish |
| `delete_selection` | Delete it; the products stay |

**Checkout**

| Tool | |
|---|---|
| `get_checkout` | The order being formed: payment methods, pay-on-delivery, destinations, pickup points, shipments, points, totals |
| `configure_checkout` | Set payment, points, pay-on-delivery and pickup point in one call |
| `place_order` | **Spends money.** Submit, waiting until the order exists |
| `pay_order` | Charge an order left unpaid, and report what is left to do |
| `list_cancel_reasons` | Reasons Ozon accepts for cancelling |
| `cancel_order` | Cancel an order, or named items of it, returning them to the cart |

**Session and money**

| Tool | |
|---|---|
| `session_status` | Whether the session acts as the account, and which gates are open |
| `start_login` / `submit_login_code` | Restore a dead session with a one-time code |
| `get_finances` | Ozon Card balance and total points |
| `get_points` | Points by type, burning points, per-store seller bonuses |

Changing the account is off by default. `OZON_ENABLE_WRITES=1` allows the cart,
favorites, lists and cancellations; `OZON_ENABLE_ORDERS=1` allows `place_order`
and is separate because it spends money. `session_status` reports both, so a
caller can plan around them instead of finding out halfway through.

## What a caller needs to know

Some of Ozon's behaviour does not follow from a tool's name.

**The cart ticks are the order.** `get_checkout` reports nothing orderable until
something is ticked, and it orders exactly what is ticked — so "buy these two"
is `select_cart_items(skus, mode="only")`, whatever else the cart holds. Ozon's
checkout is a snapshot of those ticks taken when checkout is entered, and only an
entry replaces it: unticking an item afterwards changes the cart and not the
order. `get_checkout` and `place_order` therefore enter checkout before reading,
which keeps the options already chosen.

**Two money figures, never interchangeable.** `totals.total` is what Ozon charges
today; `totals.order_total` is what the order costs. On a pay-on-delivery order
today's charge is 0 ₽, so `order_total` is the figure to quote to a person.

**An order row has no total.** Ozon prints none on the order list, so a row
carries `amount_due_at_pickup` («К оплате при получении») and, per item, that
item's price and `paid`. The sum owed on collection is not any item's price, and
`paid` is `null` when Ozon says nothing — which is not unpaid.

**«Текущие заказы» is not a list of current orders.** Ozon keeps the recently
received and cancelled ones on that page. `scope="active"` leaves them out;
`state` says which of the three a row is.

**Pay-on-delivery is not all-or-nothing.** Ozon defers payment per shipment, so
an order can be part deferred and part prepaid — an imported item usually has to
be paid up front. `pay_after_receipt.scope` is `full`, `partial` or `none`; on a
partial order `pay_now_items` and `pay_on_receipt_items` name the lines on each
side, as Ozon splits them.

**Wishlists and «Подборки» are different things.** A wishlist has a numeric id
and holds anything. A selection has a uuid, a cover, a description and a
visibility; its products come from favorites only, and publishing puts it on the
account owner's public profile after review. Its products are a separate read —
the list states a count — and Ozon has no "add" of its own: the form submits the
whole list, which is what `add_to_selection` / `remove_from_selection` do around
the current contents.

**Cancelling works line by line.** `cancel_order(order, skus=[...])` drops those
items and leaves the rest of the order standing, in as many passes as it has
items.

**A card charge finishes on Ozon's bank domain**, which signs the account in to
the bank. `pay_order` drives the payment to that point and reports what remains:
the amount, how much to top the card up by, and the page to finish at.
Pay-on-delivery avoids the whole thing.

**Errors carry a code as well as a sentence** — `[rate_limited]`,
`[session_expired]`, `[writes_disabled]`, `[orders_disabled]`,
`[total_mismatch]`, `[upstream_unavailable]`. Branch on the code; the sentence is
written to be relayed to a person. A failure never arrives as an empty result: a
502 or a timeout raises, because "no orders" and "Ozon did not answer" are
different answers.

## Configuration

| Variable | Default | |
|---|---|---|
| `OZON_PROFILE_DIR` | `/data/profile` | Persistent Chromium profile holding the session |
| `OZON_PROFILE_BACKUP` | `/data/profile.backup` | Copy of a known-good profile, restored on a sign-out |
| `OZON_STATE_PATH` | `/data/state.json` | Legacy cookie snapshot, imported once to seed a new profile |
| `OZON_IMPERSONATE` | `chrome124` | curl_cffi TLS-impersonation profile |
| `OZON_ENABLE_WRITES` | `0` | Allow cart / favorites / list / cancellation changes |
| `OZON_ENABLE_ORDERS` | `0` | Allow `place_order` — spends money |
| `OZON_MONITOR_STORE` | `/data/price_history.json` | Favorites price-history file |
| `OZON_REQUEST_TIMEOUT` | `30` | Seconds for one HTTP call |
| `OZON_REQUEST_ATTEMPTS` | `3` | Attempts before a call is reported as failed |
| `OZON_RETRY_BACKOFF_SECONDS` | `1` | Base wait between attempts, doubled and jittered |
| `OZON_RETRY_CAP_SECONDS` | `20` | Longest wait, including a `Retry-After` Ozon asks for |
| `OZON_BROWSER_TIMEOUT` | `60` | Seconds for a browser navigation or a login step |
| `OZON_IDLE_SECONDS` | `600` | Close the idle browser; the HTTP session stays |
| `OZON_TRANSPORT` | `stdio` | `stdio` (client spawns the process), `http` (streamable HTTP at `/mcp`) or `sse` (deprecated, `/sse`) |
| `OZON_HOST` / `OZON_PORT` | `0.0.0.0` / `8084` | Bind for the HTTP transports; the same port serves `/metrics` |
| `OZON_ALLOWED_HOSTS` | `[]` | `Host` headers `sse` accepts; empty means any. Naming hosts turns on MCP's exact-match check |

See `env.example`.

## Running

```bash
docker build -t ozon-mcp .

# stdio: the client attaches to the container's stdin/stdout
docker run -i --rm --shm-size=1g -v /opt/ozon-mcp:/data ozon-mcp

# http: long-lived service on :8084 (/mcp + /metrics)
docker run -d --name ozon-mcp --shm-size=1g -v /opt/ozon-mcp:/data \
  -e OZON_TRANSPORT=http -p 8084:8084 ozon-mcp
```

`/data` has to be a bind mount. It holds the profile, and Ozon rotates the
session constantly: cookies rotated over HTTP are pushed back into the profile so
the refresh chain survives a restart. On an ephemeral directory the login is lost
on every container recreation.

> **The profile is a credential.** It grants full access to the account —
> orders, addresses, card balance, checkout. Never commit it; back it up
> encrypted.

Locally, with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run playwright install --with-deps chromium
uv run python -m ozon_mcp   # needs a display or Xvfb
```

Under `http` and `sse` the same port serves Prometheus metrics at `/metrics`: upstream
request outcomes and latency, antibot re-challenges, session bootstraps, browser
state.

## Session lifetime

A signed-out session looks exactly like an empty account — no orders, no
balances, no explanation — so every tool raises instead of answering,
`session_status` reports the state, and `start_login` / `submit_login_code`
restore it with a one-time code that only the account owner receives.

A profile known to be signed in is copied, and a sign-out is recovered from
that copy automatically, so in most cases nobody is asked for a code.

## Several agents at once

Multiple clients can connect over the HTTP transports, and each gets its own MCP session. They
share one Ozon account and one worker thread, which has two consequences.

Calls are serialised: a second agent waits out the first, including a
13-second browser bootstrap.

More importantly, **the account state is shared**. Cart ticks live on Ozon's
side, not in the MCP session, so two agents composing orders at once overwrite
each other's selection — and `place_order` buys whatever is ticked at that
moment, at a total the caller read a second earlier. Reads are safe for any
number of agents; writes are not. Keep one writer per account.

The endpoint has no authentication: whoever reaches the port has the account.

## Limitations

- Only saved addresses can be chosen. `configure_checkout` switches between the
  points in the account's address book; adding one from the map is not
  implemented.
- A selection's cover cannot be uploaded; that is a multipart upload and is not
  covered.
- Per-shipment destinations are handled but unverified against a live order Ozon
  actually split across addresses.
- `pay_order` cannot complete a card charge: that happens on Ozon's bank domain
  and needs banking credentials this server does not hold.
- Placing an order spends real money, and is gated separately from every other
  write.

## Development

```bash
make check-all   # ruff format --check, ruff check, ty, pytest with a coverage gate
```

`ty` runs with `all = "error"`, ruff with `select = ["ALL"]` and a curated ignore
list. Tests mirror `src/`; the service layer is driven through a stand-in for
`get_session()` and the transport through a stand-in for the HTTP session, so
nothing in the suite touches the network.

## Disclaimer

Scraping a personal account is against Ozon's Terms of Service. This project is
for personal, low-volume use, and you are responsible for how you use it.

## License

[MIT](LICENSE)
