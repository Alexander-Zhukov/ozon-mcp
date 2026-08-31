"""Fixed OZON endpoints and request shapes (no tuning knobs — those live in
``settings``). Kept here as ``Final`` so call sites read intent, not magic.
"""

from __future__ import annotations

from typing import Final

HOME_URL: Final = "https://www.ozon.ru/"
# Two page-JSON backends: composer serves the main pages; entrypoint serves the
# "second container" lazy sections (product description, search facets) and the
# favorites/purchases scroll pagination.
COMPOSER_URL: Final = "https://www.ozon.ru/api/composer-api.bx/page/json/v2?url="
ENTRYPOINT_URL: Final = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url="
ACTION_URL: Final = "https://www.ozon.ru/api/composer-api.bx/_action/"

# Chromium flags that get past OZON's Variti antibot when running headed/Xvfb.
LAUNCH_ARGS: Final = (
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
)
# Client-hint headers the antibot requires alongside a Chrome TLS fingerprint and
# valid cookies; harvested from a live browser request and replayed by curl_cffi.
HARVEST_HEADERS: Final = frozenset({
    "accept-language",
    "referer",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "user-agent",
})

# The special favorites list id (0xFFFFFFFF) that holds all purchased items.
PURCHASES_LIST_ID: Final = 4294967294

# Friendly sort name -> OZON `sorting=` value, for search / browse.
SEARCH_SORTS: Final = {
    "popular": "",
    "new": "new",
    "cheap": "price",
    "expensive": "price_desc",
    "rating": "rating",
    "discount": "discount",
}
# Friendly sort name -> `sorting=` value, for the purchases list.
PURCHASE_SORTS: Final = {
    "newest": "new",
    "oldest": "old",
    "cheap": "price",
    "discount": "discount",
}

# Per-widget endpoint. Some blocks on a page arrive empty and are filled by a
# second call naming the widget state; the delivery estimate is one of them.
WIDGET_URL: Final = "https://www.ozon.ru/api/composer-api.bx/widget/json/v2?widgetStateId="

# The component descriptor the site posts to fetch webDelivery, captured from a
# live page load. Version-pinned by Ozon's layout, so the caller falls back to
# reading the rendered page if this stops returning a state.
WEB_DELIVERY_STATE_ID: Final = "webDelivery-8727767-default-1"
WEB_DELIVERY_CI: Final = {
    "view": {"name": "webDelivery", "vertical": "pdp", "version": 7},
    "vertical": "pdp",
    "name": "webDelivery",
    "params": [
        {"name": "foodPreOrder", "bool": True},
        {"name": "theme", "text": "default"},
        {
            "name": "holidaysNotificationText",
            "text": "Сроки доставки увеличены, так как склад продавца не работает в праздники",
        },
        {"name": "holidaysNotificationLinkText", "text": "Посмотреть товары других продавцов"},
        {"name": "digitalProductMode"},
        {"name": "multipleDeliveries", "bool": True},
        {"name": "checkOldSkuOffers"},
        {"name": "isSkeletonEnabled"},
        {"name": "hiddenDeliveryWidget"},
    ],
    "version": 8,
    "layoutID": 11852,
    "id": 8727767,
}
