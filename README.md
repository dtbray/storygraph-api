# Storygraph API
A python package to interact with and fetch data from the [StoryGraph](https://app.thestorygraph.com/) website.

## Features
- **Book Details**: Fetch detailed information about a book using its unique ID.
- **Search**: Perform a book search on StoryGraph and retrieve the results.
- **Fetch User lists**: 
    -  currently reading
    -  planning to read
    -  books read

## Installation
```
pip install storygraph-api
```

## Getting Started

The API is divided into two components, `Books Client` and   `User Client`.

### Authentication

StoryGraph does not currently provide a public API. Authenticated requests use
the same cookies as a logged-in browser session. On a trusted Linux machine,
the client can load those cookies from an installed browser:

```python
from storygraph_api import Book, User

books = Book.from_browser()  # auto-detect
user = User.from_browser("firefox")

print(user.currently_reading("sampleuname"))
print(books.search("pride and prejudice"))
```

The selected browser must have an active remembered StoryGraph login. Supported
browsers are Firefox, Chrome, Chromium, Brave, Edge, Vivaldi, Opera, and Safari.
Pass both a browser name and profile path when automatic discovery selects the
wrong profile:

```python
books = Book.from_browser("chromium", profile="~/.config/chromium/Profile 2")
```

`from_firefox(profile)` remains available as a compatibility alias backed by
the native Firefox cookie loader. Cookie values are read into memory and are
never written by this package.

For services that do not run alongside Firefox, pass cookies from a secret
manager instead:

```python
from storygraph_api import User

user = User(
    cookies={
        "_storygraph_session": "...",
        "remember_user_token": "...",
    }
)
```

StoryGraph rotates `_storygraph_session` during normal requests. The client
keeps those updates for its lifetime. A browser-backed client reloads browser
cookies once when a request indicates that authentication has expired.

### Authenticated Read Methods

```python
user.get_user_id("sampleuname")
user.currently_reading("sampleuname")
user.to_read("sampleuname")
user.up_next("sampleuname")
user.books_read("sampleuname")
user.get_all_journal_entries()

books.book_info(book_id)
books.search("search terms")
books.reading_progress(book_id)
books.get_journal_entries(book_id)
books.get_read_dates(book_id)
books.get_ai_summary(book_id, user_id)
```

Shelf and journal methods follow StoryGraph pagination until no new records are
returned. Read methods do not modify StoryGraph. The authenticated book client
also offers explicit progress and status writes:

```python
books.update_status(book_id, "currently-reading")
books.update_progress(book_id, 42)
books.update_status(book_id, "read")
```

These use StoryGraph's private web endpoints and may need updates if its forms
change. Mutating requests are never automatically retried.

### Audiobookshelf progress sync

The bundled worker matches Audiobookshelf items to StoryGraph, sends monotonic
percentage updates, and marks completed books as read. It is dry-run by default:

```bash
export AUDIOBOOKSHELF_URL=https://abs.example.com
export AUDIOBOOKSHELF_TOKEN=...
export STORYGRAPH_REMEMBER_TOKEN=...
export STORYGRAPH_SESSION=...  # optional but recommended

storygraph-audiobookshelf-sync
storygraph-audiobookshelf-sync --apply --loop --interval 900
```

Mappings and last-sent progress are kept in `/data/state.json` by default.
Matching prefers ISBN and ASIN searches and only accepts an unambiguous result.
The worker never moves StoryGraph progress backward. New progress resumes paused
books as currently reading, while DNF books are left alone. Mount `/data`
persistently when running the container.

Ambiguous matches can be reviewed in an optional, accessible web interface:

```bash
export MATCH_REVIEW_USERNAME=...
export MATCH_REVIEW_PASSWORD=...
storygraph-audiobookshelf-sync --apply --loop --review-port 8080
```

The review interface lists the best StoryGraph candidates and the reason for
each score. Confirmed mappings and ignored books are persisted in the same state
file as progress. Confirming, retrying, or undoing a match wakes the worker for
an immediate sync. The interface requires HTTP Basic authentication, protects
write actions with a CSRF token, and should only be exposed through HTTPS or a
trusted authenticated reverse proxy.

### Book Details:

```python
# Books Client
# Fetch details of a book using its ID

from storygraph_api import Book

id = "fbdd6b7c-f512-47f2-aa94-d8bf0d5f5175"
book = Book.from_firefox()
result = book.book_info(id)
print(result)
```
#### Result:
```json
{
  "title": "Hagakure: The Book of the Samurai",
  "authors": [
    "Yamamoto Tsunetomo",
    "William Scott Wilson"
  ],
  "pages": "179",
  "first_pub": "1716",
  "tags": [
    "nonfiction",
    "history",
    "philosophy",
    "informative",
    "reflective",
    "slow-paced"
  ],
  "average_rating": "3.65",
  "description": "<div><em>Hagakure<\\/em> (\\\"In the Shadow of Leaves\\\") is a manual for the samurai classes consisting of a series of short anecdotes and reflections that give both insight and instruction-in the philosophy and code of behavior that foster the true spirit of Bushido-the Way of the Warrior. It is not a book of philosophy as most would understand the word: it is a collection of thoughts and sayings recorded over a period of seven years, and as such covers a wide variety of subjects, often in no particular sequence. <br><br>The work represents an attitude far removed from our modern pragmatism and materialism, and possesses an intuitive rather than rational appeal in its assertion that Bushido is a Way of Dying, and that only a samurai retainer prepared and willing to die at any moment can be totally true to his lord. While <em>Hagakure<\\/em> was for many years a secret text known only to the warrior vassals of the Hizen fief to which the author belonged, it later came to be recognized as a classic exposition of samurai thought and came to influence many subsequent generations, including Yukio Mishima. <br><br>This translation offers 300 selections that constitute the core texts of the 1,300 present in the original. <br><em>Hagakure<\\/em> was featured prominently in the film <em>Ghost Dog<\\/em>, by Jim Jarmusch.<\\/div>",
  "warnings": {
    "graphic": [
      "Suicide",
      "Violence"
    ],
    "moderate": [
      "Suicide",
      "Suicide attempt",
      "War"
    ],
    "minor": [
      "Gore"
    ]
  }
}
```


### User List:

```python
from storygraph_api import User

user = User.from_browser()
result = user.currently_reading("sampleuname")
print(result)
```

#### Result:
  
  ```json
  [
    {
        "title": "The Murder After the Night Before",
        "book_id": "38cb5b56-23f1-48fd-b4b3-a80e07a19775",
        "authors": ["Katie Brent"]
    },
    {
        "title": "The Graces",
        "book_id": "653b54b3-a79d-4c2e-ae40-eae281a91315",
        "authors": ["Laure Eve"]
    }
]

  ```

## Further Information

Refer to [books_client.py](storygraph_api/books_client.py) and
[users_client.py](storygraph_api/users_client.py) for the public methods. Browser
authentication requires a remembered StoryGraph login and is read from the
selected browser at runtime.

## Contributing
Contributions are welcome! Fork the repository, make your changes, and submit a pull request.

For bugs or feature requests, please open an issue on [GitHub](https://github.com/ym496/storygraph-api/issues).

Install the package with its development dependencies, then run the same checks
used in CI:

```bash
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
python -m build
pip-audit .
```

Ruff provides both linting and formatting for this project. Run `ruff check
--fix .` and `ruff format .` before submitting changes.

## License

This project is licensed under the MIT License.
