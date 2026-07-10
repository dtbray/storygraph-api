import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from storygraph_api import Book, User
from storygraph_api.exception_handler import request_exception
from storygraph_api.exceptions import RequestError
from storygraph_api.request.books_request import BooksScraper
from storygraph_api.request.user_request import UserScraper

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_book_client_success_contract_is_json():
    with patch(
        "storygraph_api.books_client.BooksParser.search",
        return_value=[{"title": "Example Book"}],
    ):
        assert json.loads(Book().search("example")) == [{"title": "Example Book"}]


def test_book_client_request_error_contract_is_json():
    with patch(
        "storygraph_api.books_client.BooksParser.search",
        side_effect=RequestError("not available"),
    ):
        assert json.loads(Book().search("example")) == {"error": "not available"}


def test_shelf_pagination_collects_new_records_until_empty_page():
    pages = {
        1: fixture("shelf.html"),
        2: """
            <div class='book-title-author-and-series'>
              <a href='/books/book-two'>Second Book</a>
              <a href='/authors/author-two'>Author Two</a>
            </div>
            <div class='book-title-author-and-series'>
              <a href='/books/book-three'>Third Book</a>
              <a href='/authors/author-three'>Author Three</a>
            </div>
        """,
        3: "",
    }

    def fetch(_uname, _cookie, _transport, page):
        return pages[page]

    result = User(transport=object())._fetch_paginated(fetch, "example")
    assert [book["book_id"] for book in result] == [
        "book-one",
        "book-two",
        "book-three",
    ]


def test_shelf_pagination_stops_on_repeated_page():
    fetch = Mock(return_value=fixture("shelf.html"))
    result = User(transport=object())._fetch_paginated(fetch, "example")
    assert len(result) == 2
    assert fetch.call_count == 2


def test_journal_pagination_keeps_distinct_entries_without_ids():
    with patch(
        "storygraph_api.request.user_request.UserScraper.journal",
        side_effect=[fixture("journal.html"), ""],
    ):
        entries = json.loads(User(transport=object()).get_all_journal_entries())
    assert len(entries) == 4
    assert len([entry for entry in entries if entry["entry_id"] is None]) == 2


def test_request_decorator_wraps_request_failures_only():
    @request_exception
    def network_failure():
        raise requests.ConnectionError("offline")

    @request_exception
    def programming_failure():
        raise TypeError("bug")

    with pytest.raises(RequestError):
        network_failure()
    with pytest.raises(TypeError):
        programming_failure()


def test_book_path_segment_is_encoded():
    transport = Mock()
    response = Mock(content=b"ok")
    transport.get.return_value = response
    assert BooksScraper.main("../private", transport) == b"ok"
    transport.get.assert_called_once_with(
        "https://app.thestorygraph.com/books/..%2Fprivate"
    )


def test_username_path_segment_is_encoded():
    transport = Mock()
    response = Mock(text="ok")
    transport.get.return_value = response
    assert UserScraper.get_profile_page("name/other", transport=transport) == "ok"
    transport.get.assert_called_once_with(
        "https://app.thestorygraph.com/profile/name%2Fother"
    )
