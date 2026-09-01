"""Parse catalog widgets into DTOs: tiles, product cards, reviews, facets."""

import re
from typing import Any, Final

from ozon_mcp.models.catalog import (
    Characteristic,
    Description,
    FilterOption,
    ProductCard,
    Review,
    Reviews,
    SearchFilter,
    Tile,
    Variant,
    VariantOption,
)
from ozon_mcp.parsing.common import (
    IMAGE_RE,
    PRICE_RE,
    find_all,
    prices,
    state_by_layout,
    walk,
    widget,
    widget_with,
)
from ozon_mcp.utils.serde import dumps, loads


def _tile_title(item: dict[str, Any]) -> str | None:
    """The product name, from the atom Ozon marks as the name.

    A tile also carries badges, stock lines and seller labels; picking the
    longest string instead — which is what this did — hands back "4 577 шт
    осталось" for a product whose name is shorter than its stock notice.
    """
    for atom in walk(item):
        if atom.get("id") == "name" or (atom.get("testInfo") or {}).get("automatizationId") == "tile-name":
            text = _atom_text(atom)
            if text:
                return text
    texts = [text for text in find_all(item, "text") if isinstance(text, str)]
    return max((text for text in texts if len(text) > 8), key=len, default=None)


def _atom_text(atom: dict[str, Any]) -> str | None:
    candidates: list[Any] = [atom.get("text"), *(value for value in atom.values() if isinstance(value, dict))]
    for value in candidates:
        if isinstance(value, str):
            return str(value).strip() or None
        if isinstance(value, dict):
            nested = value.get("text")
            if isinstance(nested, str) and str(nested).strip():
                return str(nested).strip()
    return None


def _tile_prices(item: dict[str, Any]) -> tuple[str | None, str | None]:
    """Current and pre-discount price, told apart by the style Ozon gives them.

    ``priceV2`` labels them ``PRICE`` and ``ORIGINAL_PRICE``; taking the first
    two money-looking strings in the tile instead depends on their order in the
    payload, which is not the caller's business to rely on.
    """
    for node in walk(item):
        entries = node.get("price") if isinstance(node.get("price"), list) else None
        if not entries:
            continue
        current = next((e.get("text") for e in entries if isinstance(e, dict) and e.get("textStyle") == "PRICE"), None)
        original = next(
            (e.get("text") for e in entries if isinstance(e, dict) and e.get("textStyle") == "ORIGINAL_PRICE"), None
        )
        if current or original:
            first = str(current).strip() if isinstance(current, str) else None
            second = str(original).strip() if isinstance(original, str) else None
            return (first or None, second or None)
    found: list[str] = [str(match) for match in PRICE_RE.findall(dumps(item))]
    return (found[0] if found else None, found[1] if len(found) > 1 else None)


def parse_tiles(data: dict[str, Any]) -> list[Tile]:
    """Product tiles from a tileGridDesktop / search grid.

    A tile states its own sku, and its name and prices sit in atoms Ozon labels
    — so all three are read from those rather than recognised by shape.
    """
    state = widget(data, "tileGridDesktop") or widget(data, "searchResultsV2") or {}
    tiles: list[Tile] = []
    for item in (state.get("items") if isinstance(state, dict) else None) or []:
        if not isinstance(item, dict):
            continue
        declared = item.get("sku") or item.get("skuId") or item.get("id")
        sku = str(declared) if declared and str(declared).isdigit() else None
        if sku is None:
            found = re.search(r"/product/[a-z0-9\-]+-(\d{6,})/", dumps(item))
            sku = found.group(1) if found else None
        price, price_old = _tile_prices(item)
        tiles.append(
            Tile(
                sku=sku,
                title=_tile_title(item),
                price=price,
                price_old=price_old,
                url=f"https://www.ozon.ru/product/{sku}/" if sku else None,
            )
        )
    return tiles


def parse_gallery(data: dict[str, Any]) -> list[str]:
    """All product photo URLs (webGallery + webListPhotos covers)."""
    blob = dumps(widget(data, "webGallery") or {}) + dumps(widget(data, "webListPhotos") or {})
    return list(dict.fromkeys(IMAGE_RE.findall(blob)))


def parse_characteristics(data: dict[str, Any]) -> list[Characteristic]:
    """Name/value pairs from webShortCharacteristics."""
    state = widget_with(data, "webShortCharacteristics", "characteristics") or {}
    out: list[Characteristic] = []
    for item in (state.get("characteristics") if isinstance(state, dict) else None) or []:
        if not isinstance(item, dict):
            continue
        name = next(iter(find_all(item.get("title") or {}, "content")), None)
        values = [v.get("text") for v in item.get("values") or [] if isinstance(v, dict)]
        if name:
            out.append(Characteristic(name=name, value=", ".join(t for t in values if t)))
    return out


def parse_product(data: dict[str, Any]) -> ProductCard:
    """Product card: title, price, variants (each a purchasable SKU), photos."""
    heading = widget(data, "webProductHeading") or {}
    price_widget = widget(data, "webPrice") or {}
    aspects = widget(data, "webAspects") or {}
    sku_widget = widget(data, "webDetailSKU") or {}

    variants: list[Variant] = []
    for group in (aspects.get("aspects") if isinstance(aspects, dict) else None) or []:
        name = group.get("aspectName") or group.get("aspectKey")
        options: list[VariantOption] = []
        for variant in group.get("variants") or []:
            if not isinstance(variant, dict):
                continue
            label = next(
                (
                    t
                    for t in find_all(variant.get("data") or {}, "content") + find_all(variant, "text")
                    if isinstance(t, str) and t.strip()
                ),
                None,
            )
            options.append(
                VariantOption(
                    sku=variant.get("sku"),
                    label=label,
                    price=variant.get("price"),
                    availability=variant.get("availability"),
                    link=variant.get("link"),
                )
            )
        if name:
            variants.append(Variant(name=name, options=options))

    return ProductCard(
        title=heading.get("title") or next(iter(find_all(heading, "text")), None),
        sku=next(iter(find_all(sku_widget, "sku")), None) or next(iter(find_all(sku_widget, "text")), None),
        price=next(iter(prices(price_widget)), None),
        price_list=prices(price_widget),
        variants=variants,
        characteristics=parse_characteristics(data),
        photos=parse_gallery(data),
    )


def parse_reviews(data: dict[str, Any]) -> Reviews:
    """Reviews from /product/<sku>/reviews/: score + individual reviews."""
    score = [s for s in find_all(widget(data, "webReviewProductScore") or {}, "text") if isinstance(s, str)][:3]
    reviews: list[Review] = []
    all_photos: list[str] = []
    listing = widget(data, "webListReviews") or {}
    for review in (listing.get("reviews") if isinstance(listing, dict) else None) or []:
        if not isinstance(review, dict):
            continue
        content = review.get("content") or {}
        text = " ".join(t for t in (content.get("comment"), content.get("positive"), content.get("negative")) if t)
        photos = [p.get("url") for p in content.get("photos") or [] if p.get("url")]
        all_photos += photos
        reviews.append(
            Review(
                author=(review.get("author") or {}).get("firstName"),
                score=content.get("score"),
                text=text[:800] or None,
                date=review.get("publishedAt"),
                photos=photos,
            )
        )
    return Reviews(score=score, count=len(reviews), photos=list(dict.fromkeys(all_photos)), reviews=reviews[:30])


def parse_description(sku: str, data: dict[str, Any]) -> Description:
    """Description text + embedded images from the webDescription widget.

    Not in the main /product/ composer JSON — it lives in the entrypoint second
    container (?layout_container=pdpPage2column&layout_page_index=2).

    Ozon writes it two ways: ``richAnnotation`` is plain HTML (the common case),
    ``richAnnotationJson`` a structured block of text nodes. Both are handled,
    since a seller's choice between them is invisible from the outside.
    """
    # The layout says which of the two webDescription widgets is the description;
    # the payload check is only a fallback for responses without a layout.
    state = state_by_layout(data, "webDescription", descriptionMode="full")
    if state is None:
        state = widget_with(data, "webDescription", "richAnnotation", "richAnnotationJson") or {}
    chunks: list[str] = []

    plain = state.get("richAnnotation")
    if isinstance(plain, str) and plain.strip():
        chunks.append(plain)

    rich = state.get("richAnnotationJson")
    if isinstance(rich, str):
        try:
            rich = loads(rich)
        except ValueError:
            rich = None
    if rich:
        for content in find_all(rich, "content") + find_all(rich, "text"):
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                chunks += [item for item in content if isinstance(item, str)]

    joined = re.sub(r"<[^>]+>", " ", " ".join(dict.fromkeys(chunk for chunk in chunks if len(chunk) > 3)))
    joined = re.sub(r"\s+", " ", joined).strip()
    images = list(dict.fromkeys(IMAGE_RE.findall(dumps(state))))
    return Description(sku=sku, description=joined or None, images=images)


def parse_filters(data: dict[str, Any]) -> list[SearchFilter]:
    """Facets from filtersDesktop.sections[].filters[] (entrypoint 2nd container).

    Options live in ``sections[].items[]`` (key + title.text). Apply via
    ``search(filters={filter.key: option.value})``; ranges via ``{key: "min;max"}``.
    """
    state = widget(data, "filtersDesktop") or {}
    out: list[SearchFilter] = []
    for section in (state.get("sections") if isinstance(state, dict) else None) or []:
        for facet in section.get("filters") or []:
            if not isinstance(facet, dict):
                continue
            kind, key = facet.get("type"), facet.get("key")
            spec = facet.get(kind) if isinstance(facet.get(kind), dict) else {}
            if isinstance(spec.get("rangeFilter"), dict):
                spec = spec["rangeFilter"]
            title = spec.get("title")
            if isinstance(title, dict):
                title = title.get("text") or next(iter(find_all(title, "text")), None)
            options = _facet_options(spec)
            entry = SearchFilter(name=title, key=key, type=kind, options=options)
            if spec.get("minValue") is not None or spec.get("maxValue") is not None:
                entry.range = [spec.get("minValue"), spec.get("maxValue")]
            if title or options or entry.range:
                out.append(entry)
    return out


def _facet_options(spec: dict[str, Any]) -> list[FilterOption]:
    options: list[FilterOption] = []
    for section in spec.get("sections") or []:
        for item in section.get("items") or []:
            label = item.get("title")
            if isinstance(label, dict):
                label = label.get("text") or next(iter(find_all(label, "text")), None)
            options.append(FilterOption(label=label, value=item.get("key"), selected=item.get("isSelected") or None))
    options.extend(
        FilterOption(label=category.get("title"), value=category.get("key"), category_link=category.get("link"))
        for category in spec.get("categories") or []
        if isinstance(category, dict)
    )
    return options[:40]


# Roles Ozon assigns its own sections in cellTrackingInfo.uis; everything else
# listed there is a delivery option.
_ADDRESS_ROLE: Final = "main"
_RETURN_ROLE: Final = "returnInfo"


def _section_lines(section: dict[str, Any]) -> list[str]:
    """The text lines of a webDelivery section, in the order it renders them."""
    return [
        part["content"].strip()
        for part in section.get("descriptionRs") or []
        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("content"), str)
    ]


def _section_key(section: dict[str, Any]) -> str | None:
    tracking: dict[str, Any] = section.get("trackingInfo") or {}
    click: dict[str, Any] = tracking.get("click") or {} if isinstance(tracking, dict) else {}
    key = click.get("key") if isinstance(click, dict) else None
    return str(key) if key else None


def parse_delivery_widget(state: Any) -> dict[str, str | None]:
    """Delivery estimate out of the webDelivery widget state.

    The widget names the role of each section itself: ``cellTrackingInfo.uis``
    maps a role (``main`` for the chosen address, ``pvz``/``bestDelivery``/… for
    the delivery options, ``returnInfo`` for returns) to that section's tracking
    key. Resolving those keys is what makes this read the address and the date
    Ozon meant, instead of the first phrase on the page that looked like either.

    Each section states its lines in render order: the address section gives the
    address and then where it ships from, an option gives its name and then when
    it arrives.
    """
    if not isinstance(state, dict):
        return {"delivery": None, "address": None, "source": None}
    uis = (state.get("cellTrackingInfo") or {}).get("uis") if isinstance(state.get("cellTrackingInfo"), dict) else {}
    uis = uis if isinstance(uis, dict) else {}
    sections = [section for section in state.get("sections") or [] if isinstance(section, dict)]
    by_key = {key: section for section in sections if (key := _section_key(section))}

    address_section = by_key.get(str(uis.get(_ADDRESS_ROLE)))
    address_lines = _section_lines(address_section) if address_section else []
    option_keys = [str(key) for role, key in uis.items() if role not in {_ADDRESS_ROLE, _RETURN_ROLE} and key]
    option_lines = next((lines for key in option_keys if (lines := _section_lines(by_key.get(key) or {}))), [])
    return {
        # The option's second line is the estimate; its first names the option.
        "delivery": option_lines[1] if len(option_lines) > 1 else None,
        "address": address_lines[0] if address_lines else None,
        "source": address_lines[1] if len(address_lines) > 1 else None,
    }
