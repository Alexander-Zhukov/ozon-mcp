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
import shutil
import threading
import time
from contextlib import suppress
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
from ozon_mcp.errors import OzonError, SessionExpiredError
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
# Ozon serves each login step from its own "-lite" iframe: the email or phone
# form from /ozonid-lite, the one-time code from /otp-lite.
_AUTH_FRAME_MARKERS: Final[tuple[str, ...]] = ("ozonid", "otp-lite")


def _is_auth_frame(url: str) -> bool:
    return any(marker in url for marker in _AUTH_FRAME_MARKERS)


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
        self._backup = settings.profile_backup
        self._seed_state = settings.state_path
        self._impersonate = settings.impersonate
        self._lock = threading.RLock()
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._http: Any = None
        self._headers: dict[str, str] = {}
        self._synced: dict[str, str] = {}
        self._logging_in = False
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

    def back_up_profile(self) -> None:
        """Snapshot a profile that is known to be signed in.

        Some Ozon pages sign the session out — the payment-confirmation page
        does — and with a persistent profile Chrome writes that logged-out state
        straight to disk, where no HTTP-side guard can intercept it. Without a
        copy, recovering costs another one-time code from the account owner.

        The browser is closed first, and that is the whole point: Chromium keeps
        its cookie jar in memory and writes it out when it exits, so copying the
        directory while it runs snapshots the session as it was *before* the
        login — which is how a fresh sign-in ended up backed up as a guest one.
        """
        self._close_browser()
        if not self._profile.exists():
            return
        try:
            if self._backup.exists():
                shutil.rmtree(self._backup)
            shutil.copytree(self._profile, self._backup, ignore=shutil.ignore_patterns("Singleton*"))
            logger.info("backed up the signed-in profile to %s", self._backup)
        except OSError:
            logger.warning("could not back up the profile", exc_info=True)

    def restore_profile(self) -> bool:
        """Put the last signed-in profile back, if one was kept."""
        if not (self._backup / "Default").exists():
            return False
        self._close_browser()
        try:
            if self._profile.exists():
                shutil.rmtree(self._profile)
            shutil.copytree(self._backup, self._profile)
        except OSError:
            logger.warning("could not restore the profile", exc_info=True)
            return False
        logger.info("restored the signed-in profile from %s", self._backup)
        return True

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
        if not self._browser_is_signed_in():
            # A page signed the profile out; put the kept copy back rather than
            # asking the account owner for another code.
            if self.restore_profile():
                SESSION_BOOTSTRAPS.labels(reason="restored").inc()
                self._launch_browser()
            if not self._browser_is_signed_in() and not self._logging_in:
                # Answering anyway would look like an empty account.
                raise SessionExpiredError
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

    def _browser_is_signed_in(self) -> bool:
        """Whether the profile still holds a session, judged by its own cookie."""
        try:
            user = next((c for c in self._context.cookies() if c["name"] == "__Secure-user-id"), None)
        except Exception:
            return False
        return bool(user and user.get("value") not in {"", _GUEST_USER_ID})

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

    def post_page(self, path: str, body: object, backend: Backend = "composer") -> dict[str, Any]:
        """POST a page-level command and get the refreshed page back.

        Some controls are not ``_action`` endpoints: the site posts to the
        page's own JSON URL and re-renders from the response. Which backend
        serves it depends on the page — the cart posts to composer, the checkout
        to entrypoint — and posting to the wrong one silently changes nothing.
        """
        base = ENTRYPOINT_URL if backend == "entrypoint" else COMPOSER_URL
        # The inner path is a *value* of the endpoint's url= parameter, so its
        # own query has to be escaped: left raw, its parameters detach and act
        # on the endpoint instead, and the command silently does nothing.
        return self._request("POST", base + quote(path, safe="/"), body=body, backend=backend)

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

    # -- interactive login ---------------------------------------------------
    def _auth_frame(self) -> Any:
        """The iframe holding the current login step; wait for it to appear.

        The step changes the iframe: the email form is served from
        ``/ozonid-lite`` and, once the address is submitted, Ozon swaps in
        ``/otp-lite`` for the code. Matching only the first URL made the code
        step look like a vanished login form, so a login begun in one call could
        never be completed in another.
        """
        for _ in range(30):
            frame = next((frame for frame in self._page.frames if _is_auth_frame(frame.url or "")), None)
            if frame is not None:
                return frame
            self._page.wait_for_timeout(1000)
        msg = "OzonID login frame never appeared"
        raise OzonError(msg)

    def begin_login(self, login: str) -> str:
        """Open the login form and ask Ozon to send a one-time code.

        The code is delivered out of band, so this returns as soon as it has
        been requested; ``complete_login`` finishes the job.
        """
        with self._lock:
            self._logging_in = True
            self._close_browser()
            self._launch_browser()
            self._page.goto(HOME_URL + "my/orderlist", wait_until="domcontentloaded", timeout=60_000)
            self._page.wait_for_timeout(6_000)
            self._page.get_by_role("button", name="войти", exact=False).first.click(timeout=15_000)
            frame = self._auth_frame()
            self._page.wait_for_timeout(2_500)
            by_mail = "@" in login
            if by_mail:
                frame.get_by_text("Войти по почте", exact=False).first.click(timeout=8_000)
                self._page.wait_for_timeout(2_500)
                frame = self._auth_frame()
                frame.locator("input[type=email]").first.fill(login)
            else:
                frame.locator("input").first.fill(login)
            frame.get_by_role("button", name="Войти", exact=True).first.click(timeout=8_000)
            self._page.wait_for_timeout(5_000)
            return "email" if by_mail else "phone"

    def complete_login(self, code: str) -> bool:
        """Type the one-time code and report whether the account is signed in.

        The code field can arrive ``disabled`` and updates from a React handler
        on that very input, so digits only register if the input is the event
        target: it is enabled and focused first, then real keystrokes are sent.
        """
        with self._lock:
            frame = self._auth_frame()
            frame.evaluate(
                "() => { const el = document.querySelector('input');"
                " if (el) { el.disabled = false; el.removeAttribute('disabled'); el.focus(); } }"
            )
            self._page.keyboard.type(re.sub(r"\D", "", code), delay=140)
            self._page.wait_for_timeout(1_500)
            with suppress(Exception):
                button = frame.get_by_role("button", name="Войти", exact=True).first
                if button.is_enabled(timeout=1_500):
                    button.click(timeout=2_500)
            for _ in range(20):
                self._page.wait_for_timeout(1_000)
                if not any(_is_auth_frame(frame.url or "") for frame in self._page.frames):
                    break
            self._page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60_000)
            self._page.wait_for_timeout(4_000)
            signed_in = self._browser_is_signed_in()
            if signed_in:
                # Closes the browser, which flushes the new session to the
                # profile; the next call relaunches against it.
                self.back_up_profile()
                self._http = None
            self._logging_in = not signed_in
            return signed_in

    def signed_in_user(self) -> str | None:
        """The account id the profile currently holds, if any."""
        with self._lock:
            self._ensure_browser()
            cookie = next((c for c in self._context.cookies() if c["name"] == "__Secure-user-id"), None)
            value = (cookie or {}).get("value")
            return str(value) if value and value != _GUEST_USER_ID else None

    def has_backup(self) -> bool:
        return (self._backup / "Default").exists()

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
