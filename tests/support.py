"""A session stand-in, so the service layer can be tested without Ozon.

The services reach Ozon through one dependency, ``get_session()``, and that is
the seam the tests replace — the factory, not the methods on it.
"""

from __future__ import annotations

from typing import Any

from ozon_mcp.utils.serde import dumps


def page(**widgets: Any) -> dict[str, Any]:
    """A page the way Ozon serves it: widget states as JSON strings."""
    return {"widgetStates": {f"{name}-1-default-1": dumps(state) for name, state in widgets.items()}}


class FakeSession:
    """Answers with scripted pages and records what was asked for.

    ``pages`` is matched by substring so a test can key on the part of the path
    it cares about; ``actions`` the same for action names. An unscripted call
    answers with an empty page rather than raising, because most tests care
    about one call and not about the rest of the walk.
    """

    def __init__(self) -> None:
        self.pages: dict[str, Any] = {}
        self.actions: dict[str, Any] = {}
        self.fetched: list[str] = []
        self.performed: list[tuple[str, Any]] = []
        self.posted: list[tuple[str, Any]] = []

    def _match(self, table: dict[str, Any], key: str) -> Any:
        for pattern, answer in table.items():
            if pattern in key:
                return answer() if callable(answer) else answer
        return {"widgetStates": {}}

    def fetch(self, path: str, backend: str = "composer") -> dict[str, Any]:
        self.fetched.append(path)
        return self._match(self.pages, path)

    def action(self, name: str, body: Any = None) -> dict[str, Any]:
        self.performed.append((name, body))
        return self._match(self.actions, name)

    def post_page(self, path: str, body: Any = None, backend: str = "composer") -> dict[str, Any]:
        self.posted.append((path, body))
        return self._match(self.pages, path)

    def widget_state(self, state_id: str, async_data: str) -> dict[str, Any]:
        self.fetched.append(f"widget:{state_id}")
        return self._match(self.pages, state_id)

    def page_extract(self, path: str, script: str) -> Any:
        self.fetched.append(f"render:{path}")
        return None

    def signed_in_user(self) -> str | None:
        return "44563249"

    def has_backup(self) -> bool:
        return True
