import requests

from storygraph_api.exception_handler import request_exception


class BooksScraper:
    @staticmethod
    @request_exception
    def fetch_url(url, transport=None):
        response = transport.get(url) if transport else requests.get(url, timeout=20)
        response.raise_for_status()
        return response.content

    @staticmethod
    def main(book_id, transport=None):
        url = f"https://app.thestorygraph.com/books/{book_id}"
        return BooksScraper.fetch_url(url, transport)

    @staticmethod
    def community_reviews(book_id, transport=None):
        url = f"https://app.thestorygraph.com/books/{book_id}/community_reviews"
        return BooksScraper.fetch_url(url, transport)

    @staticmethod
    def content_warnings(book_id, transport=None):
        url = f"https://app.thestorygraph.com/books/{book_id}/content_warnings"
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
