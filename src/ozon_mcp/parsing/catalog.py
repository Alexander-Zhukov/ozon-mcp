"""Parse catalog widgets into DTOs: tiles, product cards, reviews, facets."""

from __future__ import annotations

import json
import re
from typing import Any

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
from ozon_mcp.parsing.common import IMAGE_RE, PRICE_RE, find_all, prices, widget


def parse_tiles(data: dict[str, Any]) -> list[Tile]:
    """Product tiles from a tileGridDesktop / search grid."""
    state = widget(data, "tileGridDesktop") or widget(data, "searchResultsV2") or {}
    tiles: list[Tile] = []
    for item in (state.get("items") if isinstance(state, dict) else None) or []:
        blob = json.dumps(item, ensure_ascii=False)
        sku_match = re.search(r"/product/[a-z0-9\-]+-(\d{6,})/", blob)
        sku = sku_match.group(1) if sku_match else None
        texts = [t for t in find_all(item, "text") if isinstance(t, str)]
        title = max((t for t in texts if len(t) > 8), key=len, default=None)
        found = PRICE_RE.findall(blob)
        tiles.append(
            Tile(
                sku=sku,
                title=title,
                price=found[0] if found else None,
                price_old=found[1] if len(found) > 1 else None,
                url=f"https://www.ozon.ru/product/{sku}/" if sku else None,
            )
        )
    return tiles


def parse_gallery(data: dict[str, Any]) -> list[str]:
    """All product photo URLs (webGallery + webListPhotos covers)."""
    blob = json.dumps(widget(data, "webGallery") or {}, ensure_ascii=False) + json.dumps(
        widget(data, "webListPhotos") or {}, ensure_ascii=False
    )
    return list(dict.fromkeys(IMAGE_RE.findall(blob)))


def parse_characteristics(data: dict[str, Any]) -> list[Characteristic]:
    """Name/value pairs from webShortCharacteristics."""
    state = widget(data, "webShortCharacteristics") or {}
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
    """
    state = widget(data, "webDescription") or {}
    rich = state.get("richAnnotationJson")
    if isinstance(rich, str):
        try:
            rich = json.loads(rich)
        except ValueError:
            rich = None
    chunks: list[str] = []
    for content in find_all(rich or state, "content") + find_all(rich or state, "text"):
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            chunks += [c for c in content if isinstance(c, str)]
    joined = re.sub(r"<[^>]+>", " ", " ".join(dict.fromkeys(c for c in chunks if len(c) > 3)))
    joined = re.sub(r"\s+", " ", joined).strip()
    images = list(dict.fromkeys(IMAGE_RE.findall(json.dumps(state, ensure_ascii=False))))
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


_DELIVERY_TERM_RE = re.compile(r"(?:С|с)\s+\d{1,2}\s+\w+|Доставим[^,.]{0,40}|Послезавтра|Завтра|Сегодня")


def parse_delivery_widget(state: Any) -> dict[str, str | None]:
    """Delivery estimate out of the webDelivery widget state.

    The widget is a list of sections (address, terms, returns); the term is the
    first date-ish phrase in them, and the address explains what it is relative
    to — the estimate is meaningless without it.
    """
    texts = [
        t.strip() for t in find_all(state, "content") + find_all(state, "text") if isinstance(t, str) and t.strip()
    ]
    term = next((m.group(0) for text in texts if (m := _DELIVERY_TERM_RE.search(text))), None)
    address = next((text for text in texts if re.search(r"ул\.|просп|Пункт|д\.\s*\d", text)), None)
    source = next((text for text in texts if "склад" in text.lower()), None)
    return {"delivery": term, "address": address, "source": source}
