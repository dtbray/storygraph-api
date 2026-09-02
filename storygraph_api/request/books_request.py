from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from storygraph_api.exception_handler import request_exception
from storygraph_api.exceptions import RequestError


class BooksScraper:
    @staticmethod
    @request_exception
    def fetch_url(url, transport=None):
        response = transport.get(url) if transport else requests.get(url, timeout=20)
        response.raise_for_status()
        return response.content

    @staticmethod
    def main(book_id, transport=None):
        url = f"https://app.thestorygraph.com/books/{quote(str(book_id), safe='')}"
        return BooksScraper.fetch_url(url, transport)

    @staticmethod
    def community_reviews(book_id, transport=None):
        url = (
            "https://app.thestorygraph.com/books/"
            f"{quote(str(book_id), safe='')}/community_reviews"
        )
        return BooksScraper.fetch_url(url, transport)

    @staticmethod
    def content_warnings(book_id, transport=None):
        url = (
            "https://app.thestorygraph.com/books/"
            f"{quote(str(book_id), safe='')}/content_warnings"
        )
        return BooksScraper.fetch_url(url, transport)

    @staticmethod
    def journal(book_id, transport):
        return transport.get("/journal", params={"book_id": book_id}).content

    @staticmethod
    def personalized_preview(book_id, user_id, transport):
        return transport.get(
            "/personalized-preview.turbo_stream",
            params={"book_id": book_id, "personalized": "false", "user_id": user_id},
        ).content

    @staticmethod
    def search(query, transport=None):
        if transport:
            response = transport.get(
                "/search",
                params={"search_term": query, "turbo_frame": "search_results"},
            )
            return response.content
        response = requests.get(
            "https://app.thestorygraph.com/browse",
            params={"search_term": query},
            timeout=20,
        )
        response.raise_for_status()
        return response.content

    @staticmethod
    def _book_page_and_csrf(book_id, transport):
        encoded_id = quote(str(book_id), safe="")
        response = transport.get(f"/books/{encoded_id}")
        soup = BeautifulSoup(response.content, "html.parser")
        token = soup.select_one('meta[name="csrf-token"]')
        csrf = token.get("content") if token else None
        if not csrf:
            raise RequestError("StoryGraph did not provide a CSRF token.")
        total = soup.select_one("input.read-status-book-num-of-pages")
        total_pages = total.get("value", "0") if total else "0"
        return csrf, total_pages

    @staticmethod
    @request_exception
    def update_progress(book_id, percent, transport):
        csrf, total_pages = BooksScraper._book_page_and_csrf(book_id, transport)
        encoded_id = quote(str(book_id), safe="")
        return transport.request(
            "POST",
            "/update-progress",
            data={
                "read_status[progress_number]": str(percent),
                "read_status[progress_type]": "percentage",
                "read_status[book_num_of_pages]": total_pages,
                "book_id": str(book_id),
                "on_book_page": "true",
                "authenticity_token": csrf,
            },
            headers={
                "X-CSRF-Token": csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "text/javascript, application/javascript, */*; q=0.01",
                "Referer": f"https://app.thestorygraph.com/books/{encoded_id}",
            },
        )

    @staticmethod
    @request_exception
    def update_status(book_id, status, transport):
        csrf, _ = BooksScraper._book_page_and_csrf(book_id, transport)
        encoded_id = quote(str(book_id), safe="")
        encoded_status = quote(status, safe="-")
        return transport.request(
            "POST",
            f"/update-status.js?book_id={encoded_id}&status={encoded_status}",
            data={"authenticity_token": csrf},
            headers={
                "X-CSRF-Token": csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "text/javascript, application/javascript, */*; q=0.01",
                "Referer": f"https://app.thestorygraph.com/books/{encoded_id}",
            },
        )
