"""The storefront: search, product cards, reviews, delivery estimates."""

from typing import Annotated

from pydantic import Field

from ozon_mcp.dependencies import run_blocking
from ozon_mcp.mcp_server import mcp
from ozon_mcp.models.catalog import Cheaper, DeliveryEstimate, Description, ProductCard, Reviews, SearchFilter, Tile
from ozon_mcp.services import catalog
from ozon_mcp.utils.annotations import Limit, Page, SearchSort, SkuOrUrl


@mcp.tool()
async def search(
    query: Annotated[str | None, Field(description="Search text. Give this, a category, or both.")] = None,
    category: Annotated[
        str | None,
        Field(description='A category slug from a category URL, e.g. "produkty-dlya-doma-9200".'),
    ] = None,
    sort: SearchSort = "popular",
    page: Page = 1,
    filters: Annotated[
        dict[str, str] | None,
        Field(
            description="Facets from get_search_filters(): {key: option_value} for a checkbox or category, "
            '{key: "min;max"} for a range, e.g. {"currency_price": "200;600"}.'
        ),
    ] = None,
) -> list[Tile]:
    """Storefront search → product tiles (sku/title/price/url). Give a text
    query, a category slug ("produkty-dlya-doma-9200"), or both.
    A tile is not a card: for variants, characteristics, photos and stock call
    product_details() with its sku.
    filters comes from get_search_filters() — {key: option_value} for a
    checkbox or category facet, {key: "min;max"} for a range, e.g.
    {"currency_price": "200;600"}. Narrowing by price is a filter, not a sort.
    """
    return await run_blocking(lambda: catalog.search(query, category, sort, page, filters))


@mcp.tool()
async def get_search_filters(
    query: Annotated[str, Field(description="The same search text whose facets you want.")],
) -> list[SearchFilter]:
    """Facets available for a query: {name, key, type, options|range}. Apply them
    with search(filters={key: value}) — checkbox/category value = option.value,
    range value = "min;max". Flow: search → get_search_filters → search(filters).
    """
    return await run_blocking(lambda: catalog.get_search_filters(query))


@mcp.tool()
async def product_details(
    sku_or_url: SkuOrUrl,
    with_description: Annotated[
        bool,
        Field(description="Also fetch the description text and its images (one extra request)."),
    ] = False,
    with_reviews: Annotated[
        bool,
        Field(description="Also fetch the reviews (one extra request)."),
    ] = False,
) -> ProductCard:
    """Product card: title, price, variants, characteristics, gallery photos.
    Each variant carries its own sku, price and availability — that sku is what
    goes into the cart, and for apparel it is the only one that will add.
    with_description / with_reviews fetch those too (separate requests each);
    get_description() and get_reviews() do the same on their own.
    """
    return await run_blocking(
        lambda: catalog.product_details(sku_or_url, with_description=with_description, with_reviews=with_reviews)
    )


@mcp.tool()
async def get_reviews(sku_or_url: SkuOrUrl) -> Reviews:
    """Reviews on their own: overall score, individual reviews
    (author/score/text/date) and review photos.
    """
    return await run_blocking(lambda: catalog.get_reviews(sku_or_url))


@mcp.tool()
async def get_description(sku_or_url: SkuOrUrl) -> Description:
    """Product description text plus the images embedded in it."""
    return await run_blocking(lambda: catalog.get_description(sku_or_url))


@mcp.tool()
async def delivery_estimate(sku_or_url: SkuOrUrl) -> DeliveryEstimate:
    """When a product would arrive, to which of the account's addresses, and
    from which warehouse ("Завтра, 2 сентября" / "ул. Данилова, 17" / "Со
    склада Ozon"). The date is relative to that address, so quote both.
    This is per product, before ordering; for an existing order the dates are
    in list_orders(), and for an order being formed in get_checkout().
    """
    return await run_blocking(lambda: catalog.delivery_estimate(sku_or_url))


@mcp.tool()
async def find_cheaper(sku_or_url: SkuOrUrl, limit: Limit = 10) -> Cheaper:
    """Find the same or a similar product cheaper: takes the card's title,
    searches the storefront and returns options below the current price.
    """
    return await run_blocking(lambda: catalog.find_cheaper(sku_or_url, limit))
