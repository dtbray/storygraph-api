from pathlib import Path
from unittest.mock import patch

from storygraph_api.parse.books_parser import BooksParser
from storygraph_api.parse.user_parser import UserParser

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_book_page_fixture_covers_full_read_model():
    with (
        patch(
            "storygraph_api.parse.books_parser.BooksScraper.main",
            return_value=fixture("book_page.html"),
        ),
        patch(
            "storygraph_api.parse.books_parser.BooksScraper.community_reviews",
            return_value=fixture("community_reviews.html"),
        ),
        patch(
            "storygraph_api.parse.books_parser.BooksScraper.content_warnings",
            return_value=fixture("content_warnings.html"),
        ),
    ):
        result = BooksParser.book_page("book-one")

    assert result == {
        "title": "Example Book",
        "authors": ["Author One", "Author Two"],
        "pages": "321",
        "first_pub": "2020",
        "tags": ["fiction", "reflective"],
        "average_rating": "4.25",
        "description": "A sanitized description.",
        "warnings": {
            "graphic": ["Violence"],
            "moderate": ["Injury"],
            "minor": ["Blood"],
        },
    }


def test_content_warnings_missing_sections_returns_empty_groups():
    with patch(
        "storygraph_api.parse.books_parser.BooksScraper.content_warnings",
        return_value="<div class='standard-pane'></div>",
    ):
        assert BooksParser.content_warnings("book-one") == {
            "graphic": [],
            "moderate": [],
            "minor": [],
        }


def test_search_fixture():
    with patch(
        "storygraph_api.parse.books_parser.BooksScraper.search",
        return_value=fixture("search.html"),
    ):
        assert BooksParser.search("example") == [
            {"title": "Example Book", "author": "Author One", "book_id": "book-one"},
            {"title": "Second Book", "author": "Author Two", "book_id": "book-two"},
        ]


def test_reading_progress_fixture():
    with patch(
        "storygraph_api.parse.books_parser.BooksScraper.main",
        return_value=fixture("progress.html"),
    ):
        assert BooksParser.reading_progress("book-one", object()) == {
            "status": "currently reading",
            "progress_pages": 42,
            "progress_percent": 21,
            "total_pages": 200,
        }


def test_personalized_preview_fixture():
    with patch(
        "storygraph_api.parse.books_parser.BooksScraper.personalized_preview",
        return_value=fixture("preview.html"),
    ):
        assert BooksParser.personalized_preview("book-one", "user-one", object()) == {
            "summary": "A personalized preview."
        }


def test_shelf_fixture_deduplicates_responsive_markup():
    assert UserParser.parse_html(fixture("shelf.html")) == [
        {"title": "Example Book", "book_id": "book-one", "authors": ["Author One"]},
        {"title": "Second Book", "book_id": "book-two", "authors": ["Author Two"]},
    ]


def test_profile_and_up_next_fixtures():
    with patch(
        "storygraph_api.parse.user_parser.UserScraper.get_profile_page",
        return_value=fixture("profile.html"),
    ):
        assert UserParser.get_user_id("example") == {"user_id": "user-uuid"}
    with patch(
        "storygraph_api.parse.user_parser.UserScraper.to_read",
        return_value=fixture("up_next.html"),
    ):
        assert UserParser.up_next("example") == [
            {
                "title": "Queued Book",
                "book_id": "up-next-book",
                "authors": ["Queued Author"],
            }
        ]


def test_journal_fixture_covers_ids_progress_pages_and_notes():
    entries = UserParser.journal_entries(fixture("journal.html"))
    assert len(entries) == 4
    assert entries[0] == {
        "entry_id": "entry-one",
        "book_title": "Example Book",
        "book_id": "book-one",
        "date": "1 January 2026",
        "status": "Started reading",
        "progress_percent": 10,
        "pages_read_this_session": 10,
        "total_pages_read": 10,
        "total_pages": 100,
        "note": "A note.",
    }
    assert entries[1]["entry_id"] is None
    assert entries[-1]["status"] == "Finished"


def test_read_dates_normalizes_fixture_dates():
    with patch.object(
        BooksParser,
        "journal_entries",
        return_value=UserParser.journal_entries(fixture("journal.html")),
    ):
        assert BooksParser.read_dates("book-one", object()) == {
            "start_date": "2026-01-01",
            "finish_date": "2026-01-04",
        }
