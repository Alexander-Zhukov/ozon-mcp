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
cookies + client-hint headers). Thereafter every read/write goes out over
[`curl_cffi`](https://github.com/lexiforest/curl_cffi) (Chrome TLS
impersonation) as direct HTTP — no browser per call. The browser is reused only
for token refresh and the few DOM-rendered reads.

Requirements: run from a **Russian IP** (Ozon blocks datacenter/VPN egress) and
provide a saved logged-in session (`state.json`).

## Tools

| Tool | Description |
|---|---|
| `list_orders` | Orders (active / completed archive / all) with status, ETA, date, totals, thumbnails |
| `orders_by_date` | Completed orders within an ISO date range |
| `order_products` | SKUs of one order (order → product card) |
| `list_purchases` | Full purchase history (sorted by date / price) |
| `search_purchases` | Fast server-side search within purchases |
| `search` | Storefront search with sort and facet filters |
| `get_search_filters` | Available facets (category / brand / price range / …) for a query |
| `browse_category` | Products of a category by slug |
| `product_details` | Title, price, variants (color/size), characteristics, photos |
| `get_photos` | All product photos |
| `get_reviews` | Reviews with score, text, dates and photos |
| `get_characteristics` | Product characteristics (name/value) |
| `get_description` | Product description text + embedded images |
| `delivery_estimate` | Delivery ETA for a product |
| `find_cheaper` | Find the same/similar product cheaper |
| `get_cart` | Cart contents with quantities |
| `add_to_cart` / `remove_from_cart` / `set_cart_quantity` | Cart changes (gated) |
| `list_favorites` | Favorites as product tiles |
| `favorites_price_snapshot` / `check_favorite_price_drops` | Favorites price monitoring |
| `list_collections` / `list_wishlists` | Collections and wishlists |
| `get_lists` | Collections/wishlists with ids |
| `add_to_list` / `remove_from_list` | List membership (gated) |
| `set_favorite` | Add/remove from favorites (gated) |
| `list_returns` | Buyer returns |
| `get_finances` | Ozon Card balance and total points |
| `get_points` | Points by type + burning + per-store seller bonuses |

Mutation tools are **disabled by default** — set `OZON_ENABLE_WRITES=1` to allow
them.

## Session and state

Login uses Ozon's email + push/flash-call 2FA, so it is a **manual, one-time
onboarding** that produces `state.json` (a Playwright storage state). Point the
server at it with `OZON_STATE`.

**`/data` must be a bind mount.** The session is not static: Ozon rotates the
access/refresh cookies, and the server writes `state.json` back after every
call so the refresh chain survives a restart. If that directory is ephemeral,
the rotated session is lost on container recreation and you are back to a
manual 2FA login. Mount a real host directory:

```bash
-v /opt/ozon-mcp:/data
```

`/data` holds two files: `state.json` (the session) and `price_history.json`
(favorites price snapshots).

> **`state.json` is a credential.** It grants full access to the account —
> orders, addresses, card balance. Treat it like a password: `0600`, never
> commit it, back it up encrypted.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `OZON_STATE` | `/data/state.json` | Path to the saved authenticated session |
| `OZON_IMPERSONATE` | `chrome124` | curl_cffi TLS-impersonation profile |
| `OZON_ENABLE_WRITES` | `0` | Allow cart/favorites/list mutations |
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

**Checkout is out of reach, by Ozon's design.** The server can fill and read the
cart, but it cannot place an order. Pressing "Перейти к оформлению" lands on
`/gocheckout/login`, a three-step wizard (Авторизация → Доставка → Оформление)
whose first step is a **full OzonID re-authentication** in an iframe: phone plus
a one-time code by SMS, call or email (or VK ID / Gosuslugi). This is a step-up
gate specific to checkout — the same session reads orders, balances and writes to
the cart without complaint.

Everything past that gate is therefore unreachable, which includes:

- choosing a pickup point or delivery slot,
- selecting a payment method,
- placing the order.

Note the consequence for payment options: the payment step cannot be *read*
either, so this project makes **no claim** about which methods (pay-on-delivery,
instalments, …) are available for an account — that screen simply cannot be
opened without a human entering a code.

Other constraints:

- **A Russian IP is required.** Ozon blocks datacenter and VPN egress.
- **A real Chromium is required** for the bootstrap; headless is detected.
- The session is a credential, and it rotates — see [Session and state](#session-and-state).

## Disclaimer

Scraping a personal account is against Ozon's Terms of Service; this project is
for personal, low-volume use. You are responsible for how you use it.

## License

[MIT](LICENSE)
