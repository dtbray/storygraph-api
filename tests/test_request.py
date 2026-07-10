import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from storygraph_api.exceptions import RequestError
from storygraph_api.parse.user_parser import UserParser
from storygraph_api.request.session import (
    BrowserCookieProvider,
    StoryGraphSession,
    load_firefox_cookies,
    resolve_cookie_file,
)


class FirefoxCookieTests(unittest.TestCase):
    def test_loads_only_storygraph_authentication_cookies(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "cookies.sqlite"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE moz_cookies (host TEXT, name TEXT, value TEXT)"
            )
            connection.executemany(
                "INSERT INTO moz_cookies VALUES (?, ?, ?)",
                [
                    ("app.thestorygraph.com", "_storygraph_session", "session"),
                    ("app.thestorygraph.com", "remember_user_token", "remember"),
                    ("app.thestorygraph.com", "unrelated", "ignored"),
                    ("example.com", "remember_user_token", "ignored"),
                ],
            )
            connection.commit()
            connection.close()

            self.assertEqual(
                load_firefox_cookies(directory),
                {
                    "_storygraph_session": "session",
                    "remember_user_token": "remember",
                },
            )

    def test_requires_a_remembered_login(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "cookies.sqlite"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE moz_cookies (host TEXT, name TEXT, value TEXT)"
            )
            connection.commit()
            connection.close()

            with self.assertRaises(RequestError):
                load_firefox_cookies(directory)

    def test_browser_provider_preserves_explicit_firefox_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "cookies.sqlite"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE moz_cookies (host TEXT, name TEXT, value TEXT)"
            )
            connection.execute(
                "INSERT INTO moz_cookies VALUES (?, ?, ?)",
                ("app.thestorygraph.com", "remember_user_token", "explicit"),
            )
            connection.commit()
            connection.close()

            self.assertEqual(
                BrowserCookieProvider("firefox", directory).load(),
                {"remember_user_token": "explicit"},
            )


class StoryGraphSessionTests(unittest.TestCase):
    def test_legacy_cookie_string_sets_remember_token(self):
        transport = StoryGraphSession("remember", min_request_interval=0)
        self.assertEqual(
            transport.session.cookies.get(
                "remember_user_token", domain="app.thestorygraph.com", path="/"
            ),
            "remember",
        )

    def test_reloads_provider_cookies_once_after_auth_failure(self):
        provider = Mock()
        provider.load.return_value = {"remember_user_token": "remember"}
        transport = StoryGraphSession(cookie_provider=provider, min_request_interval=0)
        provider.reset_mock()
        forbidden = Mock(status_code=403, url="https://app.thestorygraph.com/")
        success = Mock(status_code=200, url="https://app.thestorygraph.com/")
        success.raise_for_status.return_value = None
        transport.session.request = Mock(side_effect=[forbidden, success])

        self.assertIs(transport.get("/"), success)
        provider.load.assert_called_once_with()
        self.assertEqual(transport.session.request.call_count, 2)

    def test_does_not_replay_post_after_authentication_failure(self):
        provider = Mock()
        provider.load.return_value = {"remember_user_token": "remember"}
        transport = StoryGraphSession(cookie_provider=provider, min_request_interval=0)
        provider.reset_mock()
        forbidden = Mock(status_code=403, url="https://app.thestorygraph.com/")
        transport.session.request = Mock(return_value=forbidden)

        with self.assertRaises(RequestError):
            transport.request("POST", "/update-progress")

        provider.load.assert_not_called()
        transport.session.request.assert_called_once()

    def test_refresh_replaces_stale_authentication_cookies(self):
        provider = Mock()
        provider.load.return_value = {"remember_user_token": "new-remember"}
        transport = StoryGraphSession(
            {
                "_storygraph_session": "stale-session",
                "remember_user_token": "stale-remember",
            },
            min_request_interval=0,
        )
        transport.cookie_provider = provider

        transport.refresh_cookies()

        self.assertIsNone(
            transport.session.cookies.get(
                "_storygraph_session", domain="app.thestorygraph.com", path="/"
            )
        )
        self.assertEqual(
            transport.session.cookies.get(
                "remember_user_token", domain="app.thestorygraph.com", path="/"
            ),
            "new-remember",
        )

    def test_restricts_authenticated_requests_to_storygraph(self):
        transport = StoryGraphSession("remember", min_request_interval=0)
        with self.assertRaises(RequestError):
            transport.get("https://example.com/")

    def test_wraps_network_failures(self):
        transport = StoryGraphSession("remember", min_request_interval=0)
        transport.session.request = Mock(
            side_effect=requests.ConnectionError("network unavailable")
        )
        with self.assertRaises(RequestError) as error:
            transport.get("/")
        self.assertIn("network unavailable", str(error.exception))

    def test_configures_bounded_get_only_retries(self):
        transport = StoryGraphSession("remember", min_request_interval=0, retry_total=3)
        retry = transport.session.get_adapter("https://").max_retries
        self.assertEqual(retry.total, 3)
        self.assertEqual(retry.allowed_methods, frozenset({"GET", "HEAD"}))

    def test_rejects_invalid_transport_settings(self):
        with self.assertRaises(ValueError):
            StoryGraphSession(timeout=0)
        with self.assertRaises(ValueError):
            StoryGraphSession(min_request_interval=-1)
        with self.assertRaises(ValueError):
            StoryGraphSession(retry_total=-1)


class BrowserCookieProviderTests(unittest.TestCase):
    def test_explicit_browser_filters_storygraph_authentication_cookies(self):
        cookies = [
            Mock(name="cookie", domain="app.thestorygraph.com", value="session"),
            Mock(name="cookie", domain="app.thestorygraph.com", value="remember"),
            Mock(name="cookie", domain="example.com", value="ignored"),
        ]
        cookies[0].name = "_storygraph_session"
        cookies[1].name = "remember_user_token"
        cookies[2].name = "remember_user_token"
        with patch("browser_cookie3.chromium", return_value=cookies) as loader:
            self.assertEqual(
                BrowserCookieProvider("chromium").load(),
                {
                    "_storygraph_session": "session",
                    "remember_user_token": "remember",
                },
            )
        loader.assert_called_once_with(domain_name="app.thestorygraph.com")

    def test_ignores_cookie_with_missing_domain(self):
        cookie = Mock(domain=None, value="remember")
        cookie.name = "remember_user_token"
        with patch("browser_cookie3.chromium", return_value=[cookie]):
            with self.assertRaises(RequestError):
                BrowserCookieProvider("chromium").load()

    def test_auto_browser_rejects_explicit_profile(self):
        with self.assertRaises(RequestError):
            BrowserCookieProvider("auto", "/tmp/profile")

    def test_auto_browser_skips_broken_adapter(self):
        with patch(
            "storygraph_api.request.session.SUPPORTED_BROWSERS",
            ("firefox", "chromium"),
        ):
            with patch(
                "storygraph_api.request.session.FirefoxCookieProvider.load",
                return_value={"remember_user_token": "remember"},
            ):
                with patch(
                    "browser_cookie3.chromium", side_effect=RuntimeError("broken")
                ):
                    self.assertEqual(
                        BrowserCookieProvider("auto").load(),
                        {"remember_user_token": "remember"},
                    )

    def test_auto_browser_rejects_different_logins(self):
        chromium_cookie = Mock(domain="app.thestorygraph.com", value="chromium")
        chromium_cookie.name = "remember_user_token"
        with patch(
            "storygraph_api.request.session.SUPPORTED_BROWSERS",
            ("firefox", "chromium"),
        ):
            with patch(
                "storygraph_api.request.session.FirefoxCookieProvider.load",
                return_value={"remember_user_token": "firefox"},
            ):
                with patch("browser_cookie3.chromium", return_value=[chromium_cookie]):
                    with self.assertRaisesRegex(RequestError, "select a browser"):
                        BrowserCookieProvider("auto").load()

    def test_auto_browser_allows_same_login_with_different_sessions(self):
        chromium_cookies = []
        for name, value in (
            ("remember_user_token", "same-account"),
            ("_storygraph_session", "chromium-session"),
        ):
            cookie = Mock(domain="app.thestorygraph.com", value=value)
            cookie.name = name
            chromium_cookies.append(cookie)
        with patch(
            "storygraph_api.request.session.SUPPORTED_BROWSERS",
            ("firefox", "chromium"),
        ):
            with patch(
                "storygraph_api.request.session.FirefoxCookieProvider.load",
                return_value={
                    "remember_user_token": "same-account",
                    "_storygraph_session": "firefox-session",
                },
            ):
                with patch("browser_cookie3.chromium", return_value=chromium_cookies):
                    self.assertEqual(
                        BrowserCookieProvider("auto").load()["_storygraph_session"],
                        "firefox-session",
                    )

    def test_profile_directory_resolves_chromium_network_database(self):
        with tempfile.TemporaryDirectory() as directory:
            cookie_file = Path(directory) / "Network" / "Cookies"
            cookie_file.parent.mkdir()
            cookie_file.touch()
            self.assertEqual(
                resolve_cookie_file(Path(directory), "chromium"), cookie_file
            )


class ParserRegressionTests(unittest.TestCase):
    def test_shelf_parser_uses_book_id_instead_of_series_id(self):
        html = """
        <div class="book-title-author-and-series">
          <a href="/series/1214150">A Series</a>
          <a href="/books/book-uuid">The Book</a>
          <a href="/authors/author-uuid">An Author</a>
        </div>
        """
        self.assertEqual(
            UserParser.parse_html(html),
            [
                {
                    "title": "The Book",
                    "book_id": "book-uuid",
                    "authors": ["An Author"],
                }
            ],
        )

    def test_filtered_journal_uses_requested_book_id(self):
        html = """
        <a href="/books/book-uuid">The Book</a>
        <span class="journal-entry-panes">
          <div class="mb-3 grid">
            <p class="font-semibold text-xs">8 July 2026
              <a href="/journal_entries/entry-uuid/edit">Edit</a>
            </p>
            <span title="Starting reading this book">Started reading</span>
          </div>
        </span>
        """
        self.assertEqual(
            UserParser.journal_entries(html, book_id="book-uuid"),
            [
                {
                    "entry_id": "entry-uuid",
                    "book_title": "The Book",
                    "book_id": "book-uuid",
                    "date": "8 July 2026",
                    "status": "Started reading",
                    "progress_percent": None,
                    "pages_read_this_session": None,
                    "total_pages_read": None,
                    "total_pages": None,
                    "note": None,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
