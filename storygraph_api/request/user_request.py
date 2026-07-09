from storygraph_api.exception_handler import request_exception
from storygraph_api.request.session import StoryGraphSession

class UserScraper:
    @staticmethod
    @request_exception
    def fetch_url(url, cookie=None, transport=None):
        client = transport or StoryGraphSession(cookie)
        return client.get(url).text

    @staticmethod
    def get_profile_page(uname, cookie=None, transport=None):
        return UserScraper.fetch_url(
            f"https://app.thestorygraph.com/profile/{uname}", cookie, transport
        )

    @staticmethod
    def currently_reading(uname, cookie=None, transport=None, page=None):
        url = f"https://app.thestorygraph.com/currently-reading/{uname}"
        if page:
            url = f"{url}?page={page}"
        return UserScraper.fetch_url(url, cookie, transport)

    @staticmethod
    def to_read(uname, cookie=None, transport=None, page=None):
        url = f"https://app.thestorygraph.com/to-read/{uname}"
        if page:
            url = f"{url}?page={page}"
        return UserScraper.fetch_url(url, cookie, transport)

    @staticmethod
    def books_read(uname, cookie=None, transport=None, page=None):
        url = f"https://app.thestorygraph.com/books-read/{uname}"
        if page:
            url = f"{url}?page={page}"
        return UserScraper.fetch_url(url, cookie, transport)

    @staticmethod
    def journal(cookie=None, transport=None, page=None, book_id=None):
        client = transport or StoryGraphSession(cookie)
        params = {}
        if page:
            params['page'] = page
        if book_id:
            params['book_id'] = book_id
        return client.get('/journal', params=params).text
