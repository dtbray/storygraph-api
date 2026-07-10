import re

from bs4 import BeautifulSoup

from storygraph_api.exception_handler import parsing_exception
from storygraph_api.request.user_request import UserScraper


class UserParser:
    @staticmethod
    @parsing_exception
    def get_user_id(uname, cookie=None, transport=None):
        content = UserScraper.get_profile_page(uname, cookie, transport)
        pane = BeautifulSoup(content, "html.parser").find(
            "div", id="profile-heading-pane"
        )
        user_id = pane.get("data-user-id") if pane else None
        if not user_id:
            raise ValueError(f"user ID not found for {uname}")
        return {"user_id": user_id}

    @staticmethod
    @parsing_exception
    def parse_html(html):
        soup = BeautifulSoup(html, "html.parser")
        books_list = []
        books = soup.find_all("div", class_="book-title-author-and-series")
        for book in books:
            book_link = book.find(
                "a", href=lambda href: href and href.startswith("/books/")
            )
            if not book_link:
                continue
            title = book_link.get_text(" ", strip=True)
            book_id = book_link["href"].split("/")[-1]
            authors = [
                author.get_text(" ", strip=True)
                for author in book.find_all(
                    "a", href=lambda href: href and href.startswith("/authors/")
                )
            ]
            books_list.append(
                {
                    "title": title,
                    "book_id": book_id,
                    "authors": authors,
                }
            )
        data = list(
            {(book["title"], book["book_id"]): book for book in books_list}.values()
        )
        return data

    @staticmethod
    def currently_reading(uname, cookie=None, transport=None):
        content = UserScraper.currently_reading(uname, cookie, transport)
        return UserParser.parse_html(content)

    @staticmethod
    def to_read(uname, cookie=None, transport=None):
        content = UserScraper.to_read(uname, cookie, transport)
        return UserParser.parse_html(content)

    @staticmethod
    def books_read(uname, cookie=None, transport=None):
        content = UserScraper.books_read(uname, cookie, transport)
        return UserParser.parse_html(content)

    @staticmethod
    @parsing_exception
    def up_next(uname, cookie=None, transport=None):
        content = UserScraper.to_read(uname, cookie, transport)
        soup = BeautifulSoup(content, "html.parser")
        section = soup.find("div", id="up-next-section")
        return UserParser.parse_html(str(section)) if section else []

    @staticmethod
    @parsing_exception
    def journal_entries(html, book_id=None):
        soup = BeautifulSoup(html, "html.parser")
        entries = []
        page_book_link = (
            soup.find("a", href=lambda href: href and href == f"/books/{book_id}")
            if book_id
            else None
        )
        for entry in soup.select(".journal-entry-panes > div"):
            book_link = entry.find(
                "a", href=lambda href: href and href.startswith("/books/")
            )
            resolved_book_id = (
                book_link["href"].split("/")[-1] if book_link else book_id
            )
            if not resolved_book_id:
                continue
            edit_link = entry.find("a", href=re.compile(r"^/journal_entries/.+/edit"))
            date_tag = entry.find(
                "p", class_=lambda value: value and "text-xs" in value
            )
            status_tag = entry.find("span", title=True)
            pages_tag = entry.find(
                "p", class_=lambda value: value and "clear-both" in value
            )
            pages_text = pages_tag.get_text(" ", strip=True) if pages_tag else ""
            session_match = re.search(r"(\d+) pages read", pages_text)
            total_match = re.search(r"\((\d+) pages out of (\d+)\)", pages_text)
            progress_tag = entry.find(
                class_=lambda value: value and "text-teal-500" in value
            )
            progress_match = re.search(
                r"(\d+)%",
                progress_tag.get_text(" ", strip=True) if progress_tag else "",
            )
            note = entry.find(class_="trix-content")
            entries.append(
                {
                    "entry_id": edit_link["href"].split("/")[2] if edit_link else None,
                    "book_title": (
                        book_link.get_text(" ", strip=True)
                        if book_link
                        else page_book_link.get_text(" ", strip=True)
                        if page_book_link
                        else None
                    ),
                    "book_id": resolved_book_id,
                    "date": date_tag.get_text(" ", strip=True).split(" Edit")[0]
                    if date_tag
                    else None,
                    "status": status_tag.get_text(" ", strip=True)
                    if status_tag
                    else None,
                    "progress_percent": int(progress_match.group(1))
                    if progress_match
                    else None,
                    "pages_read_this_session": int(session_match.group(1))
                    if session_match
                    else None,
                    "total_pages_read": int(total_match.group(1))
                    if total_match
                    else None,
                    "total_pages": int(total_match.group(2)) if total_match else None,
                    "note": note.get_text("\n", strip=True) if note else None,
                }
            )
        return entries
