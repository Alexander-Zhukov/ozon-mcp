"""A rating and a review count are numbers Ozon states, not ones to count.

The score used to be "the first three strings in the score widget", which came
back empty, and the count was the number of reviews on the page — so 155 847
reviews were reported as 30. Both are now read from the fields that hold them.
"""

from __future__ import annotations

from typing import Any

import pytest

from ozon_mcp.parsing.catalog import parse_reviews, reviews_next_page
from support import page

SCORE = {
    "totalScore": 4.9,
    "reviewsCount": 155847,
    "score": [
        {"title": "5 звёзд", "value": 142005},
        {"title": "4 звезды", "value": 10248},
        {"title": "1 звезда", "value": 1234},
    ],
}
REVIEW: dict[str, Any] = {
    "itemId": "2854991259",
    "publishedAt": 1788333845,
    "author": {"firstName": "Имя скрыто"},
    "usefulness": {"useful": 7, "unuseful": 1},
    "comments": {"totalCount": 2},
    "isItemPurchased": True,
    "content": {
        "score": 4,
        "comment": "Тряпочки действительно чудо",
        "positive": "Не оставляют разводов",
        "negative": "Тонкие",
        "photos": [{"url": "https://ir.ozone.ru/s3/rp-photo-13/a.jpeg"}, {"nourl": 1}],
    },
}
LISTING = {
    "reviews": [REVIEW],
    "productScore": 4.9,
    "products": {
        "2854991259": {
            "variants": [{"name": "Размер, см", "value": "30x30"}, {"name": "Цвет товара", "value": "серый"}]
        }
    },
    "paging": {"total": 155848, "page": 1, "perPage": 30, "nextButton": "?page=2&page_key=ABC&sort=usefulness_desc"},
}
PAGE = page(webReviewProductScore=SCORE, webListReviews=LISTING)


def test_the_rating_and_the_total_come_from_ozon() -> None:
    answer = parse_reviews(PAGE)
    assert answer.score == pytest.approx(4.9)
    assert answer.count == 155847
    # What came back is a separate number, and it is not the total.
    assert answer.fetched == 1


def test_the_breakdown_per_star_is_kept() -> None:
    buckets = {bucket.stars: bucket.count for bucket in parse_reviews(PAGE).distribution}
    assert buckets == {"5 звёзд": 142005, "4 звезды": 10248, "1 звезда": 1234}


def test_a_review_keeps_its_parts_apart_and_names_its_variant() -> None:
    review = parse_reviews(PAGE).reviews[0]
    assert review.text == "Тряпочки действительно чудо"
    assert review.positive == "Не оставляют разводов"
    assert review.negative == "Тонкие"
    assert review.score == 4
    assert review.date == "2026-09-02"
    assert review.useful == 7
    assert review.answers == 2
    assert review.purchased is True
    # A card's reviews cover its variants, so the review says which one.
    assert review.variant == "Размер, см: 30x30, Цвет товара: серый"
    assert review.photos == ["https://ir.ozone.ru/s3/rp-photo-13/a.jpeg"]


def test_the_next_page_is_followed_not_rebuilt() -> None:
    """The page key is opaque and tied to this walk."""
    assert reviews_next_page(PAGE) == "?page=2&page_key=ABC&sort=usefulness_desc"
    assert reviews_next_page(page(webListReviews={"reviews": []})) is None


def test_a_card_without_a_score_widget_says_nothing_rather_than_zero() -> None:
    answer = parse_reviews(page(webListReviews={"reviews": []}))
    assert answer.score is None
    assert answer.count is None
    assert answer.fetched == 0
