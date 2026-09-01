***English** · [Русский](README.ru.md)*

# Ozon MCP

[Model Context Protocol](https://modelcontextprotocol.io/) server for the
[ozon.ru](https://www.ozon.ru/) **buyer account**. Gives an LLM access to your
orders, purchase history, cart, favorites, collections/wishlists, product cards
(variants, photos, reviews, descriptions, characteristics), catalog search with
filters, and Ozon Card / points — over Ozon's internal `composer-api`.

> Unlike catalog-only scrapers, this server works under your **authenticated
> session**, so it can read personal data (orders, purchases, cart, balance) and
> — when explicitly enabled — mutate the cart and favorites.

## How it works

Ozon's Variti antibot blocks non-browser clients, so the session **bootstraps
once** with a real headed Chromium under Xvfb (passes the challenge, harvests
cookies + client-hint headers). Thereafter every read and write goes out over
[`curl_cffi`](https://github.com/lexiforest/curl_cffi) (Chrome TLS
impersonation) as direct HTTP — **no tool renders a page**, which is what makes
calls take ~0.1s instead of ~15s. The browser stays only to own the profile and
refresh the session; it is the fallback for one reading, the delivery estimate.

Requirements: run from a **Russian IP** (Ozon blocks datacenter/VPN egress) and
a persistent browser profile seeded by one interactive login.

## Tools

| Tool | Description |
|---|---|
| `list_orders` | Orders (active / archive / all), optionally within an ISO date range |
| `order_products` | Items of one order: sku, title, price paid, variant, seller |
| `purchases` | Purchase history — all of it, or a fast server-side search |
| `list_returns` | Buyer returns |
| `search` | Storefront search by text and/or category, with sort and facet filters |
| `get_search_filters` | Facets available for a query (category / brand / price range / …) |
| `product_details` | Card: price, variants, characteristics, photos; description and reviews on request |
| `get_reviews` | Reviews with score, text, dates and photos |
| `get_description` | Description text + embedded images |
| `delivery_estimate` | When it arrives, to which address, from which warehouse |
| `find_cheaper` | Find the same/similar product cheaper |
| `get_cart` | Whole cart: items, quantities, ticks, Ozon's group headings |
| `set_cart_quantity` | Set quantity; 0 removes (gated) |
| `select_cart_items` | Tick what makes up the order — only / add / remove / all / none (gated) |
| `list_favorites` | Favorites as product tiles |
| `set_favorite` | Add to / remove from favorites (gated) |
| `get_lists` | Collections and wishlists; with a sku, also their ids |
| `set_list_membership` | Put a product in a list or take it out (gated) |
| `check_favorite_price_drops` | Price diff for favorites since the previous call |
| `get_checkout` | The order being formed: payment, pay-on-delivery, destinations, pickup points, dates, points, totals |
| `configure_checkout` | Set payment, points, pay-on-delivery and pickup point in one call |
| `pay_order` | Charge an order left unpaid; returns the page where Ozon completes it |
| `place_order` | **Spends money** — submit, waiting until the order exists (gated by `OZON_ENABLE_ORDERS`) |
| `list_cancel_reasons` | Reasons Ozon accepts for cancelling an order |
| `cancel_order` | Cancel an order, returning items to the cart (gated) |
| `session_status` | Whether the stored session still acts as the account |
| `start_login` / `submit_login_code` | Restore a dead session with a one-time code |
| `get_finances` | Ozon Card balance and total points |
| `get_points` | Points by type + burning + per-store seller bonuses |

Mutation tools are **disabled by default** — set `OZON_ENABLE_WRITES=1` to allow
them.

## Session and state

**If the session dies, the tools say so.** A signed-out session otherwise looks
exactly like an empty account — no orders, no balances, no explanation — so every
tool raises instead of answering, `session_status` reports the state, and
`start_login` / `submit_login_code` restore it with a one-time code. A profile
that is known to be signed in is copied, and a sign-out is recovered from that
copy automatically, so in most cases nobody is asked for a code at all.


The session lives in a **persistent Chromium profile**, not a cookie snapshot.
That is deliberate: OzonID — the auth realm guarding checkout — keeps its
session outside cookies and localStorage, so a Playwright `storage_state`
snapshot silently loses it and checkout falls back to a login prompt. A real
profile directory keeps everything, so one login stays valid and the server
runs unattended afterwards.

Login itself (email/phone + one-time code) is a **manual, one-time onboarding**
performed once against the profile directory.

**`/data` must be a bind mount.** It holds the profile, and Ozon rotates the
session constantly — cookies rotated over HTTP are pushed back into the profile
so the refresh chain survives a restart. On an ephemeral directory you lose the
login on every container recreation.

```bash
-v /opt/ozon-mcp:/data
```

`/data` holds `profile/` (the session) and `price_history.json` (favorites price
snapshots). A legacy `state.json`, if present, is imported once to seed a brand
new profile — enough for the read tools, but not for checkout.

> **The profile is a credential.** It grants full access to the account —
> orders, addresses, card balance, and the checkout flow. Never commit it; back
> it up encrypted.

**Two things that will bite you**, both learned the hard way:

- **Refresh tokens are single-use.** Restoring an older copy of a session fails
  and lands you on an anonymous one, so an old backup is not a rollback.
- **Visiting the checkout login flow downgrades the session to a guest.** The
  server refuses to persist such a state rather than overwriting a working
  login with it.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `OZON_PROFILE_DIR` | `/data/profile` | Persistent Chromium profile holding the session |
| `OZON_STATE` | `/data/state.json` | Legacy snapshot, imported once to seed a new profile |
| `OZON_IMPERSONATE` | `chrome124` | curl_cffi TLS-impersonation profile |
| `OZON_ENABLE_WRITES` | `0` | Allow cart/favorites/list mutations |
| `OZON_ENABLE_ORDERS` | `0` | Allow `place_order` — **spends money**, gated separately |
| `OZON_MONITOR_STORE` | `/data/price_history.json` | Favorites price-history file |
| `OZON_TRANSPORT` | `stdio` | `stdio` (client spawns the process) or `sse` (HTTP service) |
| `OZON_HOST` | `0.0.0.0` | Bind address for the `sse` transport |
| `OZON_PORT` | `8084` | Port serving `/sse` and `/metrics` |

See `env.example`.

## Transports and metrics

`stdio` is the default and suits a client that launches the server itself.
`sse` runs it as a long-lived HTTP service — that is how a remote agent
attaches — and the same port also serves Prometheus metrics at `/metrics`
(upstream request outcomes, latency, antibot re-challenges, browser state).

## Run

Docker (headed Chromium + Xvfb are handled by the image):

```bash
docker build -t ozon-mcp .

# stdio: the client attaches to the container's stdin/stdout
docker run -i --rm --shm-size=1g -v /opt/ozon-mcp:/data ozon-mcp

# sse: long-lived HTTP service on :8084 (/sse + /metrics)
docker run -d --name ozon-mcp --shm-size=1g -v /opt/ozon-mcp:/data \
  -e OZON_TRANSPORT=sse -p 8084:8084 ozon-mcp
```

`--shm-size=1g` is not optional: Chromium crashes on Docker's default 64 MB
shared memory.

Locally with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run playwright install --with-deps chromium
uv run python -m ozon_mcp   # needs a display / Xvfb for the bootstrap
```

## Development

```bash
make check-all   # ruff format-check + ruff lint + ty typecheck + pytest
```

## Limitations

- **A Russian IP is required.** Ozon blocks datacenter and VPN egress.
- **A real Chromium is required** for the bootstrap; headless is detected.
- **The profile must be seeded by one interactive login.** OzonID — the auth
  realm guarding checkout — keeps state a cookie snapshot cannot carry, so the
  browser runs on a persistent profile; see [Session and state](#session-and-state).
- **Only saved addresses can be chosen.** `configure_checkout` switches between
  the points already in the account's address book; adding a new one from the
  map is not implemented.
- **Per-shipment destinations are handled but unverified.** An order can split
  into shipments with their own addresses; that path is covered by construction
  and by a unit test, not against a live multi-destination order.
- **A card charge finishes on Ozon's bank domain**, which signs the account in
  to the bank. `pay_order` drives the payment to that point and reports exactly
  what is left: the amount, how much to top the card up by if the balance falls
  short, and the page to finish at. Completing it is the account owner's step —
  this server holds no banking credentials. Pay-on-delivery avoids it entirely.
- **Do not send the browser to `finance.ozon.ru`.** That domain signs the
  session out, and because the profile is persistent Chrome writes the
  signed-out state straight to disk. A backup profile is kept and restored
  automatically, but avoid the trip.
- **Placing an order spends real money** and is gated separately from every
  other write, behind `OZON_ENABLE_ORDERS`.

## Disclaimer

Scraping a personal account is against Ozon's Terms of Service; this project is
for personal, low-volume use. You are responsible for how you use it.

## License

[MIT](LICENSE)
