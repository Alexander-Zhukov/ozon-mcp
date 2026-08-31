"""Authenticated OZON session — persistent browser profile, HTTP-served.

OZON's Variti antibot blocks non-browser clients, but a real Chromium only has
to pass the challenge **once**: harvest its cookies plus the exact client-hint
header set, and thereafter direct HTTP via curl_cffi (Chrome TLS impersonation)
reaches the authenticated composer-api / _action endpoints without a live
browser per call.

The browser runs on a **persistent profile** rather than a Playwright
``storage_state`` snapshot. storage_state only carries cookies and
localStorage; OzonID — the auth realm guarding checkout — keeps its session and
device trust outside both, so a snapshot silently drops it and checkout falls
back to a login prompt. A real profile directory keeps everything (IndexedDB,
service workers, device fingerprint), so one interactive login stays valid.

That makes the profile the single source of truth for the session, which is why
cookies rotated on the HTTP side are pushed back into the live context: Chrome
then flushes them to disk, and the refresh chain survives a restart.
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
    WIDGET_URL,
)
from ozon_mcp.settings import get_settings
from ozon_mcp.utils.observability import BROWSER_ACTIVE, SESSION_BOOTSTRAPS, UPSTREAM_LATENCY, UPSTREAM_REQUESTS

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("ozon_mcp")

_ANTIBOT = re.compile(r"antibot|ограничен|нет соединения|доступ", re.IGNORECASE)
# Cookies that carry the login; only these are worth syncing back to the browser.
_SESSION_COOKIES: Final[frozenset[str]] = frozenset({
    "__Secure-access-token",
    "__Secure-refresh-token",
    "__Secure-user-id",
    "ozonIdAuthResponseToken",
})

Backend = str  # "composer" | "entrypoint" | "action"

# OZON hands out tokens shaped "<ver>.<userId>.<secret>"; userId 0 means guest.
_GUEST_USER_ID: Final = "0"


def _outcome(status: int) -> str:
    """Bucket the status so the metric label stays low-cardinality."""
    if status == 0:
        return "error"
    if 200 <= status < 300:
        return "ok"
    return f"{status // 100}xx"


class OzonSession:
    """Persistent-profile browser plus a curl_cffi transport (thread-safe)."""

    def __init__(self, profile_dir: Path | None = None) -> None:
        settings = get_settings()
        self._profile = profile_dir or settings.profile_dir
        self._seed_state = settings.state_path
        self._impersonate = settings.impersonate
        self._lock = threading.RLock()
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._http: Any = None
        self._headers: dict[str, str] = {}
        self._synced: dict[str, str] = {}
        self._last_used = 0.0

    # -- browser lifecycle ---------------------------------------------------
    def _launch_browser(self) -> None:
        if self._page is not None:
            return
        fresh = not (self._profile / "Default").exists()
        self._profile.mkdir(parents=True, exist_ok=True)
        self._clear_stale_lock()
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._profile),
            headless=False,
            args=list(LAUNCH_ARGS),
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1366, "height": 900},
        )
        if fresh:
            self._seed_from_state()
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        BROWSER_ACTIVE.set(1)
        self._page.goto(HOME_URL, wait_until="domcontentloaded", timeout=90_000)
        self._page.wait_for_timeout(12_000)  # let Variti set cookies
        if _ANTIBOT.search((self._page.title() or "").lower()):
            self._close_browser()
            raise RuntimeError("antibot challenge not passed")

    def _clear_stale_lock(self) -> None:
        """Drop a Chromium profile lock left by a killed process.

        A profile may only be open once, and Chromium refuses to start if the
        lock is present — including when the owner died without cleaning up,
        which is exactly what happens when a container is stopped mid-call.
        """
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            lock = self._profile / name
            if lock.is_symlink() or lock.exists():
                lock.unlink(missing_ok=True)
                logger.info("removed stale profile lock %s", name)

    def _seed_from_state(self) -> None:
        """Import a legacy ``state.json`` into a brand-new profile.

        Enough to keep the read tools working without a fresh login; it cannot
        restore OzonID, so checkout still needs one interactive sign-in.
        """
        try:
            saved = json.loads(self._seed_state.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.info("no session to seed at %s; interactive login required", self._seed_state)
            return
        cookies = [c for c in saved.get("cookies") or [] if c.get("name") and c.get("domain")]
        by_name = {c["name"]: c.get("value") for c in cookies}
        if by_name.get("__Secure-user-id") == _GUEST_USER_ID:
            logger.warning("seed session at %s is anonymous; interactive login required", self._seed_state)
            return
        if cookies:
            self._context.add_cookies(cookies)
            logger.info("seeded %d cookies from %s into a fresh profile", len(cookies), self._seed_state)

    def _close_browser(self) -> None:
        for obj, method in ((self._context, "close"), (self._playwright, "stop")):
            try:
                if obj is not None:
                    getattr(obj, method)()
            except Exception:
                logger.debug("browser teardown error", exc_info=True)
        self._playwright = self._context = self._page = None
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
        self._synced = {c["name"]: c["value"] for c in self._context.cookies() if c["name"] in _SESSION_COOKIES}
        self._last_used = time.time()

    def _ensure_http(self) -> None:
        # The browser is deliberately kept alive: it owns the profile, so closing
        # it would leave HTTP-side token rotations with nowhere to be persisted.
        if self._http is None or not self._headers:
            self._bootstrap()

    def _rebootstrap(self) -> None:
        self._http = None
        self._close_browser()
        self._bootstrap(reason="rechallenge")

    # -- persistence ---------------------------------------------------------
    def save_state(self) -> None:
        """Push HTTP-rotated session cookies back into the browser profile."""
        with self._lock:
            if self._context is None or self._http is None:
                return
            jar = {c.name: c.value for c in self._http.cookies.jar}
            # Visiting the checkout login flow downgrades the session to a guest
            # one. Persisting that would overwrite a working login with an
            # anonymous token and silently lock the account out.
            if jar.get("__Secure-user-id") == _GUEST_USER_ID:
                logger.warning("session went anonymous upstream; refusing to persist it")
                return
            rotated = [
                {"name": name, "value": value, "domain": ".ozon.ru", "path": "/"}
                for name, value in jar.items()
                if name in _SESSION_COOKIES and self._synced.get(name) != value
            ]
            if not rotated:
                return
            try:
                self._context.add_cookies(rotated)
                self._synced.update({c["name"]: str(c["value"]) for c in rotated})
                logger.info("synced %d rotated cookie(s) into the profile", len(rotated))
            except Exception:
                logger.debug("cookie sync error", exc_info=True)

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

    def post_page(self, path: str, body: object) -> dict[str, Any]:
        """POST a page-level command and get the refreshed page back.

        Some controls (the cart checkboxes) are not ``_action`` endpoints: the
        site posts a command to the page's own JSON URL and re-renders from the
        response.
        """
        return self._request("POST", COMPOSER_URL + quote(path, safe="/?=&"), body=body)

    def widget_state(self, state_id: str, async_data: str) -> dict[str, Any]:
        """Fill one lazily-loaded widget by naming its state.

        The page ships such widgets empty; the site then posts a base64
        descriptor of the component to this endpoint to get the real content.
        """
        return self._request("POST", WIDGET_URL + quote(state_id, safe=""), body={"asyncData": async_data})

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
        """Navigate to ``path`` and evaluate ``js`` against the rendered DOM.

        Kept only as a fallback: everything is served over HTTP now, but the
        delivery estimate rides a layout-pinned widget endpoint, so reading the
        rendered page is the safety net if Ozon changes that layout.
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

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def is_authenticated(data: dict[str, Any]) -> bool:
        """Look for a positive signal.

        The anonymous widgets (``profileMenuAnonymous``, ``loginButton``) ship in
        the payload even for a signed-in account, so their presence proves
        nothing; a personal widget does.
        """
        blob = str(data.get("widgetStates") or {})
        return any(marker in blob for marker in ("myOrdersList", "orderList", "profileMenuUser", "userAdultModal"))
