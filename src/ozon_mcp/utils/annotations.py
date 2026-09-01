"""Argument types shared by the tools, described for the caller.

An agent sees a tool's JSON schema and its description, nothing else — so what
an argument accepts belongs in the schema, next to the argument. Naming the
choices as ``Literal`` puts them there as an enum, and the descriptions here are
written for a caller that has no other documentation.
"""

from typing import Annotated, Literal

from pydantic import Field

SkuOrUrl = Annotated[
    str,
    Field(description='A product SKU ("3077454533") or a full ozon.ru product URL. Variants have their own SKUs.'),
]
Sku = Annotated[
    str,
    Field(description='A product SKU ("3077454533"). For apparel use the variant SKU, not the base one.'),
]
OrderRef = Annotated[
    str,
    Field(
        description=(
            'An order number ("44563249-0877") — the order_number field of a list_orders() entry. '
            "Its detail_link is accepted too, since the number is encoded in it."
        )
    ),
]
Limit = Annotated[int, Field(ge=1, le=1000, description="How many entries to return at most.")]
Page = Annotated[int, Field(ge=1, description="1-based page number.")]

OrderScope = Annotated[
    Literal["active", "completed", "all"],
    Field(description='Which orders: "active" (current), "completed" (the «Завершённые» archive) or "all".'),
]
PurchaseSort = Annotated[
    Literal["newest", "oldest", "cheap", "discount"],
    Field(description="Order of the purchase history. Ignored when a query is given (Ozon ranks the search)."),
]
SearchSort = Annotated[
    Literal["popular", "new", "cheap", "expensive", "rating", "discount"],
    Field(description="How Ozon should rank the results."),
]
CartSelectMode = Annotated[
    Literal["only", "add", "remove", "all", "none"],
    Field(
        description=(
            '"only" ticks exactly these and unticks everything else — the usual way to compose an order; '
            '"add"/"remove" adjust the current ticks; "all"/"none" ignore skus.'
        )
    ),
]
IsoDate = Annotated[
    str,
    Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description='A date as YYYY-MM-DD, e.g. "2026-07-01".'),
]
