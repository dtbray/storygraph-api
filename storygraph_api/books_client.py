import json

from storygraph_api.exception_handler import handle_exceptions
from storygraph_api.parse.books_parser import BooksParser
from storygraph_api.request.books_request import BooksScraper
from storygraph_api.request.session import StoryGraphSession

READ_STATUSES = frozenset(
    {"to-read", "currently-reading", "read", "paused", "did-not-finish", "rereading"}
)


class Book:
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

    @handle_exceptions
    def book_info(self, book_id):
        data = BooksParser.book_page(book_id, self.transport)
        return json.dumps(data, indent=4)

    def _require_transport(self):
        if self.transport is None:
            raise ValueError(
                "This method requires authenticated cookies or Book.from_firefox()."
            )
        return self.transport

    @handle_exceptions
    def reading_progress(self, book_id):
        return json.dumps(
            BooksParser.reading_progress(book_id, self._require_transport()), indent=4
        )

    @handle_exceptions
    def get_journal_entries(self, book_id):
        return json.dumps(
            BooksParser.journal_entries(book_id, self._require_transport()), indent=4
        )

    @handle_exceptions
    def get_read_dates(self, book_id):
        return json.dumps(
            BooksParser.read_dates(book_id, self._require_transport()), indent=4
        )

    @handle_exceptions
    def get_ai_summary(self, book_id, user_id):
        return json.dumps(
            BooksParser.personalized_preview(
                book_id, user_id, self._require_transport()
            ),
            indent=4,
        )

    @handle_exceptions
    def search(self, query):
        data = BooksParser.search(query, self.transport)
        return json.dumps(data, indent=4)

    @handle_exceptions
    def update_progress(self, book_id, percent):
        if isinstance(percent, bool) or not isinstance(percent, int):
            raise ValueError("percent must be an integer from 0 through 100")
        if not 0 <= percent <= 100:
            raise ValueError("percent must be an integer from 0 through 100")
        BooksScraper.update_progress(book_id, percent, self._require_transport())
        return json.dumps({"book_id": str(book_id), "progress_percent": percent})

    @handle_exceptions
    def update_status(self, book_id, status):
        if status not in READ_STATUSES:
            choices = ", ".join(sorted(READ_STATUSES))
            raise ValueError(f"status must be one of: {choices}")
        BooksScraper.update_status(book_id, status, self._require_transport())
        return json.dumps({"book_id": str(book_id), "status": status})
