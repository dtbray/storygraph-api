import json
import re
from unittest.mock import Mock

import requests

from storygraph_api.audiobookshelf_sync import ProgressSync
from storygraph_api.review_server import _layout, start_review_server


def result(value):
    return json.dumps(value)


def item(item_id="abs-one"):
    return {
        "id": item_id,
        "media": {
            "metadata": {
                "title": "Example Book",
                "isbn": "9780000000001",
                "authors": [{"name": "Example Author"}],
            }
        },
    }


def sync(tmp_path, progress, *, apply=False):
    abs_client = Mock()
    abs_client.progress.return_value = [progress]
    abs_client.item.return_value = item()
    storygraph = Mock()
    storygraph.search.return_value = result(
        [{"book_id": "sg-one", "title": "Example Book", "author": "Example Author"}]
    )
    storygraph.reading_progress.return_value = result(
        {"status": "currently reading", "progress_percent": 10}
    )
    storygraph.update_progress.side_effect = lambda book_id, percent: result(
        {"book_id": book_id, "progress_percent": percent}
    )
    storygraph.update_status.side_effect = lambda book_id, status: result(
        {"book_id": book_id, "status": status}
    )
    worker = ProgressSync(abs_client, storygraph, tmp_path / "state.json", apply=apply)
    return worker, storygraph


def test_dry_run_finds_update_without_writing(tmp_path):
    worker, storygraph = sync(tmp_path, {"libraryItemId": "abs-one", "progress": 0.42})
    assert worker.run() == {"updated": 1, "unchanged": 0, "unmatched": 0, "errors": 0}
    storygraph.update_progress.assert_not_called()
    assert not (tmp_path / "state.json").exists()


def test_apply_updates_progress_and_persists_state(tmp_path):
    worker, storygraph = sync(
        tmp_path, {"libraryItemId": "abs-one", "progress": 0.42}, apply=True
    )
    worker.run()
    storygraph.update_progress.assert_called_once_with("sg-one", 42)
    assert json.loads((tmp_path / "state.json").read_text())["progress"] == {
        "abs-one": 42
    }


def test_finished_book_reaches_100_and_is_marked_read(tmp_path):
    worker, storygraph = sync(
        tmp_path,
        {"libraryItemId": "abs-one", "progress": 0.97, "isFinished": True},
        apply=True,
    )
    worker.run()
    storygraph.update_progress.assert_called_once_with("sg-one", 100)
    storygraph.update_status.assert_called_once_with("sg-one", "read")


def test_never_moves_remote_progress_backward(tmp_path):
    worker, storygraph = sync(
        tmp_path, {"libraryItemId": "abs-one", "progress": 0.09}, apply=True
    )
    assert worker.run()["unchanged"] == 1
    storygraph.update_progress.assert_not_called()


def test_finished_book_already_baselined_at_100_is_unchanged(tmp_path):
    worker, storygraph = sync(
        tmp_path,
        {"libraryItemId": "abs-one", "progress": 0.97, "isFinished": True},
        apply=True,
    )
    worker.state["progress"]["abs-one"] = 100
    assert worker.run()["unchanged"] == 1
    storygraph.update_progress.assert_not_called()
    storygraph.update_status.assert_not_called()


def test_ambiguous_match_is_skipped(tmp_path):
    worker, storygraph = sync(tmp_path, {"libraryItemId": "abs-one", "progress": 0.42})
    storygraph.search.return_value = result(
        [
            {"book_id": "sg-one", "title": "Wrong", "author": "Person"},
            {"book_id": "sg-two", "title": "Also Wrong", "author": "Person"},
        ]
    )
    assert worker.run()["unmatched"] == 1


def test_paused_book_progress_resumes_currently_reading_status(tmp_path):
    worker, storygraph = sync(
        tmp_path, {"libraryItemId": "abs-one", "progress": 0.42}, apply=True
    )
    storygraph.reading_progress.return_value = result(
        {"status": "paused", "progress_percent": 10}
    )
    worker.run()
    storygraph.update_status.assert_called_once_with("sg-one", "currently-reading")


def test_matcher_understands_implicit_book_one_suffix(tmp_path):
    worker, storygraph = sync(tmp_path, {"libraryItemId": "abs-one", "progress": 0.42})
    worker.audiobookshelf.item.return_value = {
        "id": "abs-one",
        "media": {
            "metadata": {
                "title": "Dawn of the Void",
                "authors": [{"name": "Phil Tucker"}],
            }
        },
    }
    storygraph.search.return_value = result(
        [
            {
                "book_id": "book-one",
                "title": "Dawn of the Void Book One",
                "author": "Phil Tucker",
            },
            {
                "book_id": "book-two",
                "title": "Dawn of the Void Book Two",
                "author": "Phil Tucker",
            },
        ]
    )
    worker.run()
    assert worker.state["mappings"]["abs-one"] == "book-one"


def test_matcher_rejects_tied_high_confidence_titles(tmp_path):
    worker, storygraph = sync(tmp_path, {"libraryItemId": "abs-one", "progress": 0.42})
    storygraph.search.return_value = result(
        [
            {"book_id": "a", "title": "Example Book", "author": "Example Author"},
            {"book_id": "b", "title": "Example Book", "author": "Example Author"},
        ]
    )
    assert worker.run()["unmatched"] == 1


def test_unmatched_book_is_available_for_accessible_review(tmp_path):
    worker, storygraph = sync(
        tmp_path, {"libraryItemId": "abs-one", "progress": 0.42}, apply=True
    )
    storygraph.search.return_value = result(
        [
            {
                "book_id": "candidate-one",
                "title": "Example Book: A Novel",
                "author": "Example Author",
            },
            {
                "book_id": "candidate-two",
                "title": "Different Book",
                "author": "Other Author",
            },
        ]
    )

    assert worker.run()["unmatched"] == 1
    review = worker.state["unmatched"]["abs-one"]
    assert review["item"]["title"] == "Example Book"
    matching_author = next(
        candidate
        for candidate in review["candidates"]
        if candidate["book_id"] == "candidate-one"
    )
    assert matching_author["reason"] == "Author matches; title differs"
    page = _layout(worker, "csrf-value")
    assert "Example Book" in page
    assert "candidate-one" in page
    assert 'role="status"' not in page


def test_review_actions_persist_and_wake_the_worker(tmp_path):
    worker, _ = sync(
        tmp_path, {"libraryItemId": "abs-one", "progress": 0.42}, apply=True
    )
    worker.state["unmatched"]["abs-one"] = {
        "item": {"id": "abs-one", "title": "Example Book", "author": "Author"},
        "candidates": [
            {
                "book_id": "candidate-one",
                "title": "Example Book",
                "author": "Author",
                "score": 100,
                "reason": "Exact title and author",
            }
        ],
    }

    worker.confirm_match("abs-one", "candidate-one")
    assert worker.state["mappings"]["abs-one"] == "candidate-one"
    assert worker.wake_event.is_set()
    assert json.loads((tmp_path / "state.json").read_text())["mappings"] == {
        "abs-one": "candidate-one"
    }

    worker.undo_match("abs-one")
    assert "abs-one" not in worker.state["mappings"]

    worker.state["unmatched"]["abs-one"] = {
        "item": {"id": "abs-one", "title": "Example Book", "author": "Author"},
        "candidates": [],
    }
    worker.ignore_match("abs-one")
    assert "abs-one" in worker.state["ignored"]
    worker.retry_match("abs-one")
    assert "abs-one" not in worker.state["ignored"]


def test_review_server_requires_auth_and_accepts_confirmation(tmp_path, monkeypatch):
    worker, _ = sync(
        tmp_path, {"libraryItemId": "abs-one", "progress": 0.42}, apply=True
    )
    worker.state["unmatched"]["abs-one"] = {
        "item": {"id": "abs-one", "title": "Example Book", "author": "Author"},
        "candidates": [
            {
                "book_id": "candidate-one",
                "title": "Example Book",
                "author": "Author",
                "score": 100,
                "reason": "Exact title and author",
            }
        ],
    }
    monkeypatch.setenv("MATCH_REVIEW_USERNAME", "reader")
    monkeypatch.setenv("MATCH_REVIEW_PASSWORD", "secret")
    server = start_review_server(worker, 0)
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert requests.get(url, timeout=2).status_code == 401
        page = requests.get(url, auth=("reader", "secret"), timeout=2)
        assert page.status_code == 200
        assert "Content-Security-Policy" in page.headers
        csrf = re.search('name="csrf" value="([^"]+)"', page.text).group(1)
        response = requests.post(
            f"{url}/confirm",
            auth=("reader", "secret"),
            data={
                "csrf": csrf,
                "item_id": "abs-one",
                "storygraph_id": "candidate-one",
            },
            allow_redirects=False,
            timeout=2,
        )
        assert response.status_code == 303
        assert worker.state["mappings"]["abs-one"] == "candidate-one"
    finally:
        server.shutdown()
        server.server_close()
