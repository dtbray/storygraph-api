import json
from functools import wraps

import requests

from storygraph_api.exceptions import ParsingError, RequestError, UnexpectedError


def handle_exceptions(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RequestError as e:
            return json.dumps({"error": e.message}, indent=4)
        except ParsingError as e:
            return json.dumps({"error": e.message}, indent=4)
        except Exception as e:
            raise UnexpectedError(f"Unexpected error: {str(e)}") from e

    return wrapper


def request_exception(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RequestError:
            raise
        except requests.RequestException as e:
            raise RequestError(f"StoryGraph request failed: {str(e)}") from e
        except Exception as e:
            raise RequestError(f"StoryGraph request failed: {str(e)}") from e

    return wrapper


def parsing_exception(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ParsingError:
            raise
        except Exception as e:
            raise ParsingError(
                "Failed to parse StoryGraph content; the page may have changed: "
                f"{str(e)}"
            ) from e

    return wrapper
