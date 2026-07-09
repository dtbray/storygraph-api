from __future__ import annotations

import configparser
import os
import sqlite3
import tempfile
from collections.abc import Mapping
from pathlib import Path

import requests

from storygraph_api.exceptions import RequestError


BASE_URL = "https://app.thestorygraph.com"
COOKIE_NAMES = ("_storygraph_session", "remember_user_token")


class StoryGraphSession:
    """Authenticated HTTP transport backed by StoryGraph browser cookies."""

    def __init__(
        self,
        cookies: Mapping[str, str] | str | None = None,
        *,
        timeout: float = 20,
        firefox_profile: str | os.PathLike[str] | None = None,
    ) -> None:
        self.timeout = timeout
        self.firefox_profile = Path(firefox_profile).expanduser() if firefox_profile else None
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
        if self.firefox_profile:
            self.refresh_from_firefox()

    @classmethod
    def from_firefox(
        cls,
        profile: str | os.PathLike[str] | None = None,
        *,
        timeout: float = 20,
    ) -> "StoryGraphSession":
        return cls(timeout=timeout, firefox_profile=profile or find_firefox_profile())

    def set_cookies(self, cookies: Mapping[str, str] | str) -> None:
        values = (
            {"remember_user_token": cookies}
            if isinstance(cookies, str)
            else {name: value for name, value in cookies.items() if name in COOKIE_NAMES}
        )
        for name, value in values.items():
            if value:
                self.session.cookies.set(name, value, domain="app.thestorygraph.com", path="/")

    def refresh_from_firefox(self) -> None:
        if not self.firefox_profile:
            raise RequestError("No Firefox profile is configured for cookie refresh.")
        self.set_cookies(load_firefox_cookies(self.firefox_profile))

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith(("http://", "https://")) else f"{BASE_URL}{path}"
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(method, url, **kwargs)

        if self._requires_login(response) and self.firefox_profile:
            self.refresh_from_firefox()
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

    cookies = dict(rows)
    if "remember_user_token" not in cookies:
        raise RequestError(
            "The Firefox profile is not logged into StoryGraph with a remembered session."
        )
    return cookies
