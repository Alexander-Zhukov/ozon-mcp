# Cart-only permission

Account owners must be able to add, remove, resize and select cart items without
allowing payments for existing orders, cancellations or other account changes.

Add `OZON_ENABLE_CART`, default `0`. It permits only `set_cart_quantity` and
`select_cart_items`. Preserve the existing broad `OZON_ENABLE_WRITES` permission:
either flag permits cart changes; only the broad flag permits favorites, lists,
selections, cancellations, existing-order payments and `configure_checkout`.
The latter currently has no gate; add one before any upstream work.
`OZON_ENABLE_ORDERS` continues to permit only `place_order` independently.

Report the effective cart permission as `cart_enabled` in every `SessionStatus`
response, including both login outcomes. Keep `writes_enabled` and
`orders_enabled` unchanged. Refused cart mutations use `[cart_disabled]` and
explain both operator flags; other refusals keep their existing codes.

All flags default off. Read tools keep their current behavior, including
`get_checkout` forming a checkout snapshot without placing or paying an order.
Update English/Russian READMEs, env.example and MCP-visible instructions and
tool descriptions. Document the explicit cart-only configuration and the
continued broad behavior of `OZON_ENABLE_WRITES`.

Verify real service entry points using the existing scripted session; denied
operations must make no upstream calls. Cover default-off, cart-only,
legacy-writes-only and orders-only modes, and all status/login outcomes.
Use Python >=3.13, existing dependencies and error/service conventions.
Do not enable flags on a live account, merge or deploy.
