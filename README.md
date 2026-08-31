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

## Session (one-time login)

Login uses Ozon's email + push/flash-call 2FA, so it is a **manual, one-time
onboarding** that produces `state.json` (a Playwright storage state). Point the
server at it with `OZON_STATE`. The session auto-refreshes afterwards; a full
re-login is only needed when the refresh token itself expires.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `OZON_STATE` | `/data/state.json` | Path to the saved authenticated session |
| `OZON_IMPERSONATE` | `chrome124` | curl_cffi TLS-impersonation profile |
| `OZON_ENABLE_WRITES` | `0` | Allow cart/favorites/list mutations |
| `OZON_MONITOR_STORE` | `/data/price_history.json` | Favorites price-history file |

See `env.example`.

## Run

Docker (headed Chromium + Xvfb are handled by the image):

```bash
docker build -t ozon-mcp .
docker run -i --rm --shm-size=1g -v "$PWD/data:/data" ozon-mcp
```

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

## Disclaimer

Scraping a personal account is against Ozon's Terms of Service; this project is
for personal, low-volume use. You are responsible for how you use it.

## License

[MIT](LICENSE)
