"""Authenticated OZON session — browser-bootstrapped, HTTP-served.

OZON's Variti antibot blocks non-browser clients, but a real Chromium only has
to pass the challenge **once**: harvest its cookies plus the exact client-hint
header set, and thereafter direct HTTP via curl_cffi (Chrome TLS impersonation)
reaches the authenticated composer-api / _action endpoints with no live browser
per call. The browser is kept only for bootstrap, token refresh, and the few
DOM-rendered reads (delivery estimate, подборки/вишлисты).

Session cookies rotate; they are persisted back to ``state_path`` so the refresh
chain survives. Login (2FA) is a one-time manual onboarding, not automated here.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import TYPE_CHECKING, Any, Final, Self
from urllib.parse import quote

from curl_cffi import requests as curl_requests
from playwright.sync_api import sync_playwright

from ozon_mcp.constants import (
    ACTION_URL,
    COMPOSER_URL,
    ENTRYPOINT_URL,
    HARVEST_HEADERS,
    HOME_URL,
    LAUNCH_ARGS,
)
from ozon_mcp.settings import get_settings
from ozon_mcp.utils.observability import BROWSER_ACTIVE, SESSION_BOOTSTRAPS, UPSTREAM_LATENCY, UPSTREAM_REQUESTS

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("ozon_mcp")

_ANTIBOT = re.compile(r"antibot|ограничен|нет соединения|доступ", re.IGNORECASE)
_ANONYMOUS_MARKERS: Final[tuple[str, ...]] = ("profileMenuAnonymous", "loginButton")

Backend = str  # "composer" | "entrypoint" | "action"


def _outcome(status: int) -> str:
    """Bucket the status so the metric label stays low-cardinality."""
    if status == 0:
        return "error"
    if 200 <= status < 300:
        return "ok"
    return f"{status // 100}xx"


class OzonSession:
    """Browser-bootstrapped, curl_cffi-served OZON session (thread-safe)."""

    def __init__(self, state_path: Path | None = None) -> None:
        settings = get_settings()
        self._state = state_path or settings.state_path
        self._idle = settings.idle_seconds
        self._impersonate = settings.impersonate
        self._lock = threading.RLock()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._http: Any = None
        self._headers: dict[str, str] = {}
        self._last_used = 0.0

    # -- browser lifecycle ---------------------------------------------------
    def _launch_browser(self) -> None:
        if self._page is not None:
            return
        if not self._state.exists():
            msg = f"No session at {self._state}; run the one-time login first."
            raise RuntimeError(msg)
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=False, args=list(LAUNCH_ARGS))
        self._context = self._browser.new_context(
            storage_state=str(self._state),
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1366, "height": 900},
        )
        self._page = self._context.new_page()
        BROWSER_ACTIVE.set(1)
        self._page.goto(HOME_URL, wait_until="domcontentloaded", timeout=90_000)
        self._page.wait_for_timeout(12_000)  # let Variti set cookies
        if _ANTIBOT.search((self._page.title() or "").lower()):
            self._close_browser()
            raise RuntimeError("antibot challenge not passed")

    def _close_browser(self) -> None:
        for obj, method in ((self._browser, "close"), (self._playwright, "stop")):
            try:
                if obj is not None:
                    getattr(obj, method)()
            except Exception:
                logger.debug("browser teardown error", exc_info=True)
        self._playwright = self._browser = self._context = self._page = None
        BROWSER_ACTIVE.set(0)

    def _ensure_browser(self) -> None:
        if self._page is None:
            self._launch_browser()

    # -- bootstrap: harvest cookies + headers, build the HTTP session --------
    def _bootstrap(self, reason: str = "initial") -> None:
        SESSION_BOOTSTRAPS.labels(reason=reason).inc()
        self._launch_browser()
        captured: dict[str, str] = {}

        def on_request(request: Any) -> None:
            if "composer-api.bx/page/json/v2" in request.url and not captured:
                captured.update(request.headers)

        self._page.on("request", on_request)
        self._page.evaluate(
            "async () => { await fetch('/api/composer-api.bx/page/json/v2?url=/my/orderlist',"
            " {headers: {accept: 'application/json'}, credentials: 'include'}); }"
        )
        self._page.wait_for_timeout(500)
        self._headers = {k: v for k, v in captured.items() if k.lower() in HARVEST_HEADERS}
        self._http = curl_requests.Session(impersonate=self._impersonate)
        for cookie in self._context.cookies():
            self._http.cookies.set(cookie["name"], cookie["value"], domain=".ozon.ru")
        self._last_used = time.time()

    def _ensure_http(self) -> None:
        if self._http is None or not self._headers:
            self._bootstrap()
        elif self._page is not None and self._last_used and time.time() - self._last_used > self._idle:
            self._close_browser()  # keep HTTP alive, drop the idle browser

    def _rebootstrap(self) -> None:
        self._http = None
        self._close_browser()
        self._bootstrap(reason="rechallenge")

    # -- persistence ---------------------------------------------------------
    def save_state(self) -> None:
        """Persist rotated cookies so the refresh chain survives restarts."""
        with self._lock:
            try:
                if self._context is not None:
                    self._context.storage_state(path=str(self._state))
                elif self._http is not None:
                    self._persist_http_cookies()
            except Exception:
                logger.debug("state persist error", exc_info=True)

    def _persist_http_cookies(self) -> None:
        try:
            previous = json.loads(self._state.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
        cookies = [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain or ".ozon.ru",
                "path": c.path or "/",
                "expires": c.expires or -1,
                "httpOnly": False,
                "secure": bool(c.secure),
                "sameSite": "Lax",
            }
            for c in self._http.cookies.jar
        ]
        self._state.write_text(
            json.dumps({"cookies": cookies, "origins": previous.get("origins", [])}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def close(self) -> None:
        with self._lock:
            self.save_state()
            self._close_browser()
            self._http = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- HTTP transport ------------------------------------------------------
    @staticmethod
    def _blocked(status: int, text: str) -> bool:
        return status in {403, 307} or "incidentId" in text or "abt-challenge" in text

    def _request(self, method: str, url: str, body: object = None, backend: Backend = "composer") -> dict[str, Any]:
        with self._lock:
            status, text = 0, ""
            started = time.monotonic()
            for attempt in (1, 2):
                self._ensure_http()
                headers = dict(self._headers)
                headers["accept"] = "application/json"
                if body is not None:
                    headers["content-type"] = "application/json"
                try:
                    response = self._http.request(
                        method, url, headers=headers, timeout=30, data=json.dumps(body) if body is not None else None
                    )
                    status, text = response.status_code, response.text
                # Any transport failure is retried once with a freshly bootstrapped session.
                except Exception:
                    status, text = 0, ""
                if (self._blocked(status, text) or status == 0) and attempt == 1:
                    UPSTREAM_REQUESTS.labels(backend=backend, outcome="rechallenge").inc()
                    self._rebootstrap()
                    continue
                UPSTREAM_LATENCY.labels(backend=backend).observe(time.monotonic() - started)
                UPSTREAM_REQUESTS.labels(backend=backend, outcome=_outcome(status)).inc()
                self._last_used = time.time()
                self.save_state()
                try:
                    data = json.loads(text)
                except ValueError:
                    data = {}
                data.setdefault("_httpStatus", status)
                return data
            UPSTREAM_LATENCY.labels(backend=backend).observe(time.monotonic() - started)
            UPSTREAM_REQUESTS.labels(backend=backend, outcome="failed").inc()
            return {"_httpStatus": status, "widgetStates": {}}

    def fetch(self, path: str, backend: Backend = "composer") -> dict[str, Any]:
        """Fetch a page's JSON by on-site path. backend: composer | entrypoint."""
        base = ENTRYPOINT_URL if backend == "entrypoint" else COMPOSER_URL
        return self._request("GET", base + quote(path, safe="/?=&"), backend=backend)

    def action(self, action_path: str, body: object) -> dict[str, Any]:
        """POST a composer ``_action/<action_path>`` (body sent as JSON verbatim)."""
        return self._request("POST", ACTION_URL + action_path, body=body, backend="action")

    def refresh(self) -> bool:
        """Silent session refresh (no 2FA): re-bootstrap so OZON mints a fresh
        access-token on navigation, then persist. Returns the auth state.
        """
        with self._lock:
            self._rebootstrap()
            return self.is_authenticated(self.fetch("/my/orderlist"))

    # -- DOM reads (need the browser) ----------------------------------------
    def page_extract(self, path: str, js: str, *, scroll: bool = False) -> Any:
        """Navigate to ``path`` and evaluate ``js`` against the rendered DOM, used
        for data OZON only renders client-side (e.g. delivery estimate).
        """
        with self._lock:
            self._ensure_browser()
            url = HOME_URL.rstrip("/") + path if path.startswith("/") else path
            self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            self._page.wait_for_timeout(6_000)
            if scroll:  # trigger lazy widgets
                for delta in (4000, 9000, 16000):
                    self._page.mouse.wheel(0, delta)
                    self._page.wait_for_timeout(1500)
            self._last_used = time.time()
            return self._page.evaluate(js)

    def nav_click_extract(self, path: str, click_text: str, js: str, wait_ms: int = 6000) -> Any:
        """Navigate, click the element whose text starts with ``click_text`` (a
        favorites tab), wait, then evaluate ``js`` — for session-bound sections.
        """
        with self._lock:
            self._ensure_browser()
            url = HOME_URL.rstrip("/") + path if path.startswith("/") else path
            self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            self._page.wait_for_timeout(6_000)
            self._page.evaluate(
                "(text) => { const el = [...document.querySelectorAll('a,button,span,div')]"
                ".find(e => (e.innerText || '').trim().startsWith(text)); if (el) el.click(); }",
                click_text,
            )
            self._page.wait_for_timeout(wait_ms)
            self._last_used = time.time()
            return self._page.evaluate(js)

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def is_authenticated(data: dict[str, Any]) -> bool:
        blob = str(data.get("widgetStates") or {})
        return not any(marker in blob for marker in _ANONYMOUS_MARKERS)
