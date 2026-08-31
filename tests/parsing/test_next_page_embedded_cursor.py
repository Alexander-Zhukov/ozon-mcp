"""next_page rebuilds the scroll URL from the embedded page= cursor."""

from __future__ import annotations

from ozon_mcp.parsing.common import next_page


def test_next_page_embedded_cursor() -> None:
    data = {
        "pageInfo": {"url": "/my/favorites/list?layout_page_index=2&list=42&page=111111"},
        "widgetStates": {"tile": '{"nextChunk": "/x?page=222222"}'},
    }
    following = next_page(data)
    assert following is not None
    assert "layout_page_index=3" in following
    assert "page=222222" in following
