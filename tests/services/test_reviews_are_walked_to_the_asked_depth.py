"""Reviews arrive thirty at a time, so a depth has to be walked to.

And since Ozon has no filter by star, the low-scored ones are reached by sorting
and going deep — which is why depth is a parameter rather than a page number.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ozon_mcp.services import catalog
from support import page

if TYPE_CHECKING:
    from support import FakeSession


def _listing(scores: list[int], *, following: str | None) -> dict[str, Any]:
    paging: dict[str, Any] = {"total": 155848, "page": 1, "perPage": 30}
    if following:
        paging["nextButton"] = following
    return page(
        webReviewProductScore={"totalScore": 4.9, "reviewsCount": 155848},
        webListReviews={
            "reviews": [
                {
                    "author": {"firstName": f"Автор {score}-{index}"},
                    "publishedAt": 1788333845,
                    "content": {"score": score, "comment": f"отзыв {score}-{index}"},
                }
                for index, score in enumerate(scores)
            ],
            "paging": paging,
        },
    )


def test_pages_are_walked_until_the_depth_is_met(session: FakeSession) -> None:
    pages = iter([_listing([5, 5], following="?page=2&page_key=K"), _listing([4, 3], following=None)])
    session.pages = {"/reviews/": lambda: next(pages, _listing([], following=None))}
    answer = catalog.get_reviews("2859492815", limit=4)
    assert answer.fetched == 4
    assert [review.score for review in answer.reviews] == [5, 5, 4, 3]
    # The total stays Ozon's, not the number collected.
    assert answer.count == 155848


def test_the_walk_stops_when_a_page_repeats_itself(session: FakeSession) -> None:
    """A page that keeps offering the same reviews is the end, not a loop."""
    session.pages = {"/reviews/": _listing([5, 5], following="?page=2&page_key=K")}
    answer = catalog.get_reviews("2859492815", limit=100)
    assert answer.fetched == 2


def test_the_sort_reaches_ozon_by_its_own_name(session: FakeSession) -> None:
    session.pages = {"/reviews/": _listing([1], following=None)}
    catalog.get_reviews("2859492815", limit=1, sort="worst")
    assert any("sort=score_asc" in url for url in session.fetched)
