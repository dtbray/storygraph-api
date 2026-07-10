from __future__ import annotations

import configparser
import os
import sqlite3
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import browser_cookie3
import requests

from storygraph_api.exceptions import RequestError


BASE_URL = "https://app.thestorygraph.com"
COOKIE_NAMES = ("_storygraph_session", "remember_user_token")
SUPPORTED_BROWSERS = (
    "firefox",
    "chrome",
    "chromium",
    "brave",
    "edge",
    "vivaldi",
    "opera",
    "safari",
)


class CookieProvider(Protocol):
    def load(self) -> dict[str, str]: ...


class FirefoxCookieProvider:
    def __init__(self, profile: str | os.PathLike[str] | None = None) -> None:
        self.profile = Path(profile).expanduser() if profile else find_firefox_profile()

    def load(self) -> dict[str, str]:
        return load_firefox_cookies(self.profile)


class BrowserCookieProvider:
    def __init__(
        self,
        browser: str = "auto",
        profile: str | os.PathLike[str] | None = None,
    ) -> None:
        browser = browser.lower()
        if browser != "auto" and browser not in SUPPORTED_BROWSERS:
            choices = ", ".join(("auto", *SUPPORTED_BROWSERS))
            raise RequestError(f"Unsupported browser '{browser}'. Choose one of: {choices}.")
        if browser == "auto" and profile:
            raise RequestError(
                "A browser name is required when an explicit profile path is provided."
            )
        self.browser = browser
        self.profile = Path(profile).expanduser() if profile else None

    def load(self) -> dict[str, str]:
        loader = browser_cookie3.load if self.browser == "auto" else getattr(
            browser_cookie3, self.browser
        )
        kwargs = {"domain_name": "app.thestorygraph.com"}
        if self.profile:
            kwargs["cookie_file"] = str(resolve_cookie_file(self.profile, self.browser))
        try:
            jar = loader(**kwargs)
        except Exception as exc:
            if self.browser in ("auto", "firefox"):
                try:
                    return FirefoxCookieProvider().load()
                except RequestError:
                    pass
            raise RequestError(
                f"Could not load {self.browser} browser cookies: {exc}"
            ) from exc
        cookies = {
            cookie.name: cookie.value
            for cookie in jar
            if cookie.name in COOKIE_NAMES and cookie.domain.endswith("thestorygraph.com")
        }
        if "remember_user_token" not in cookies and self.browser in ("auto", "firefox"):
            try:
                cookies = FirefoxCookieProvider().load()
            except RequestError:
                pass
        return require_remembered_login(cookies, f"{self.browser} browser")


class StoryGraphSession:
    """Authenticated HTTP transport backed by StoryGraph browser cookies."""

    def __init__(
        self,
        cookies: Mapping[str, str] | str | None = None,
        *,
        timeout: float = 20,
        firefox_profile: str | os.PathLike[str] | None = None,
        cookie_provider: CookieProvider | None = None,
    ) -> None:
        self.timeout = timeout
        self.firefox_profile = Path(firefox_profile).expanduser() if firefox_profile else None
        self.cookie_provider = cookie_provider
        if self.cookie_provider is None and self.firefox_profile:
            self.cookie_provider = FirefoxCookieProvider(self.firefox_profile)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) "
                    "Gecko/20100101 Firefox/128.0"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        if cookies:
            self.set_cookies(cookies)
        if self.cookie_provider:
            self.refresh_cookies()

    @classmethod
    def from_firefox(
        cls,
        profile: str | os.PathLike[str] | None = None,
        *,
        timeout: float = 20,
    ) -> "StoryGraphSession":
        provider = FirefoxCookieProvider(profile)
        return cls(timeout=timeout, cookie_provider=provider)

    @classmethod
    def from_browser(
        cls,
        browser: str = "auto",
        profile: str | os.PathLike[str] | None = None,
        *,
        timeout: float = 20,
    ) -> "StoryGraphSession":
        return cls(
            timeout=timeout,
            cookie_provider=BrowserCookieProvider(browser=browser, profile=profile),
        )

    def set_cookies(self, cookies: Mapping[str, str] | str) -> None:
        values = (
            {"remember_user_token": cookies}
            if isinstance(cookies, str)
            else {name: value for name, value in cookies.items() if name in COOKIE_NAMES}
        )
        for name, value in values.items():
            if value:
                self.session.cookies.set(name, value, domain="app.thestorygraph.com", path="/")

    def refresh_cookies(self) -> None:
        if not self.cookie_provider:
            raise RequestError("No browser cookie provider is configured for refresh.")
        self.set_cookies(self.cookie_provider.load())

    def refresh_from_firefox(self) -> None:
        """Backward-compatible alias for Firefox-backed sessions."""
        self.refresh_cookies()

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith(("http://", "https://")) else f"{BASE_URL}{path}"
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(method, url, **kwargs)

        if self._requires_login(response) and self.cookie_provider:
            self.refresh_cookies()
            response = self.session.request(method, url, **kwargs)

        if self._requires_login(response):
            raise RequestError(
                "StoryGraph authentication is missing or expired. Refresh the browser "
                "login and reload cookies."
            )
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RequestError(f"StoryGraph request failed: {exc}") from exc
        return response

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.request("GET", path, **kwargs)

    @staticmethod
    def _requires_login(response: requests.Response) -> bool:
        return response.status_code in (401, 403) or "/users/sign_in" in response.url


def find_firefox_profile() -> Path:
    roots = (
        Path.home() / "snap/firefox/common/.mozilla/firefox",
        Path.home() / ".mozilla/firefox",
    )
    candidates: list[Path] = []
    for root in roots:
        profiles_ini = root / "profiles.ini"
        if profiles_ini.exists():
            parser = configparser.ConfigParser()
            parser.read(profiles_ini)
            for section in parser.sections():
                if not section.startswith("Profile") or "Path" not in parser[section]:
                    continue
                path = Path(parser[section]["Path"])
                candidates.append(path if path.is_absolute() else root / path)
        candidates.extend(path.parent for path in root.glob("*/cookies.sqlite"))

    valid = {path.resolve() for path in candidates if (path / "cookies.sqlite").exists()}
    if not valid:
        raise RequestError("Could not find a Firefox profile containing cookies.sqlite.")
    return max(valid, key=lambda path: (path / "cookies.sqlite").stat().st_mtime)


def load_firefox_cookies(profile: str | os.PathLike[str]) -> dict[str, str]:
    database = Path(profile).expanduser() / "cookies.sqlite"
    if not database.exists():
        raise RequestError(f"Firefox cookie database not found: {database}")

    # Firefox may have the live database open, so query a private snapshot.
    with tempfile.TemporaryDirectory(prefix="storygraph-api-") as directory:
        snapshot = Path(directory) / "cookies.sqlite"
        source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        destination = sqlite3.connect(snapshot)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        connection = sqlite3.connect(snapshot)
        try:
            rows = connection.execute(
                "SELECT name, value FROM moz_cookies "
                "WHERE host = ? AND name IN (?, ?)",
                ("app.thestorygraph.com", *COOKIE_NAMES),
            ).fetchall()
        finally:
            connection.close()

    return require_remembered_login(dict(rows), "Firefox profile")


def require_remembered_login(cookies: dict[str, str], source: str) -> dict[str, str]:
    if "remember_user_token" not in cookies:
        raise RequestError(f"The {source} is not logged into StoryGraph with a remembered session.")
    return cookies


def resolve_cookie_file(profile: Path, browser: str) -> Path:
    if profile.is_file():
        return profile
    candidates = (
        ("cookies.sqlite",) if browser == "firefox" else ("Network/Cookies", "Cookies")
    )
    for relative_path in candidates:
        candidate = profile / relative_path
        if candidate.exists():
            return candidate
    raise RequestError(f"No cookie database found in browser profile: {profile}")
