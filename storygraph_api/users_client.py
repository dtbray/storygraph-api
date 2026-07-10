import json

from storygraph_api.exception_handler import handle_exceptions
from storygraph_api.parse.user_parser import UserParser
from storygraph_api.request.session import StoryGraphSession


class User:
    def __init__(self, cookies=None, *, firefox_profile=None, transport=None):
        self.transport = transport
        if self.transport is None and (cookies or firefox_profile):
            self.transport = StoryGraphSession(cookies, firefox_profile=firefox_profile)

    @classmethod
    def from_firefox(cls, profile=None):
        return cls(transport=StoryGraphSession.from_firefox(profile))

    @classmethod
    def from_browser(cls, browser="auto", profile=None):
        return cls(transport=StoryGraphSession.from_browser(browser, profile))

    def _fetch_paginated(self, fetch, uname, cookie=None):
        results = []
        seen = set()
        for page in range(1, 1001):
            content = fetch(uname, cookie, self.transport, page)
            books = UserParser.parse_html(content)
            new_books = [book for book in books if book["book_id"] not in seen]
            if not new_books:
                break
            results.extend(new_books)
            seen.update(book["book_id"] for book in new_books)
        return results

    @handle_exceptions
    def get_user_id(self, uname, cookie=None):
        return json.dumps(
            UserParser.get_user_id(uname, cookie, self.transport), indent=4
        )

    @handle_exceptions
    def currently_reading(self, uname, cookie=None):
        from storygraph_api.request.user_request import UserScraper

        data = self._fetch_paginated(UserScraper.currently_reading, uname, cookie)
        return json.dumps(data, indent=4)

    @handle_exceptions
    def to_read(self, uname, cookie=None):
        from storygraph_api.request.user_request import UserScraper

        data = self._fetch_paginated(UserScraper.to_read, uname, cookie)
        return json.dumps(data, indent=4)

    @handle_exceptions
    def books_read(self, uname, cookie=None):
        from storygraph_api.request.user_request import UserScraper

        data = self._fetch_paginated(UserScraper.books_read, uname, cookie)
        return json.dumps(data, indent=4)

    @handle_exceptions
    def up_next(self, uname, cookie=None):
        return json.dumps(UserParser.up_next(uname, cookie, self.transport), indent=4)

    @handle_exceptions
    def get_all_journal_entries(self, cookie=None):
        from storygraph_api.request.user_request import UserScraper

        entries = []
        seen = set()
        for page in range(1, 1001):
            page_entries = UserParser.journal_entries(
                UserScraper.journal(cookie, self.transport, page=page)
            )
            new_entries = [
                entry for entry in page_entries if entry["entry_id"] not in seen
            ]
            if not new_entries:
                break
            entries.extend(new_entries)
            seen.update(entry["entry_id"] for entry in new_entries)
        return json.dumps(entries, indent=4)
