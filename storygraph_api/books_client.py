from storygraph_api.parse.books_parser import BooksParser
from storygraph_api.exception_handler import handle_exceptions
from storygraph_api.request.session import StoryGraphSession
import json

class Book:
    def __init__(self, cookies=None, *, firefox_profile=None, transport=None):
        self.transport = transport
        if self.transport is None and (cookies or firefox_profile):
            self.transport = StoryGraphSession(cookies, firefox_profile=firefox_profile)

    @classmethod
    def from_firefox(cls, profile=None):
        return cls(transport=StoryGraphSession.from_firefox(profile))

    @handle_exceptions
    def book_info(self,book_id):
        data = BooksParser.book_page(book_id, self.transport)
        return json.dumps(data,indent=4)

    def _require_transport(self):
        if self.transport is None:
            raise ValueError('This method requires authenticated cookies or Book.from_firefox().')
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
        return json.dumps(BooksParser.read_dates(book_id, self._require_transport()), indent=4)

    @handle_exceptions
    def get_ai_summary(self, book_id, user_id):
        return json.dumps(
            BooksParser.personalized_preview(
                book_id, user_id, self._require_transport()
            ),
            indent=4,
        )

    @handle_exceptions
    def search(self,query):
        data = BooksParser.search(query, self.transport)
        return json.dumps(data,indent=4)
