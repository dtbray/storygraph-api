from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path

import requests

from storygraph_api.books_client import Book

LOG = logging.getLogger("storygraph-audiobookshelf-sync")


def _normalized(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def _title_score(local_title, candidate_title):
    local = _normalized(local_title)
    candidate = _normalized(candidate_title)
    if not local or not candidate:
        return 0
    if local == candidate:
        return 100
    if candidate.startswith(local):
        suffix = candidate[len(local) :]
        if suffix in {"1", "book1", "bookone", "vol1", "volume1", "volumeone"}:
            return 95
    return 0


class AudiobookshelfClient:
    def __init__(self, base_url, token, timeout=20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def progress(self):
        response = self.session.get(f"{self.base_url}/api/me", timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("mediaProgress", [])

    def item(self, item_id):
        response = self.session.get(
            f"{self.base_url}/api/items/{item_id}",
            params={"expanded": 1, "include": "authors"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


class ProgressSync:
    def __init__(
        self,
        audiobookshelf,
        storygraph,
        state_path,
        *,
        apply=False,
        minimum_change=2,
        finish_threshold=99,
    ):
        self.audiobookshelf = audiobookshelf
        self.storygraph = storygraph
        self.state_path = Path(state_path)
        self.apply = apply
        self.minimum_change = minimum_change
        self.finish_threshold = finish_threshold
        self.state = self._load_state()

    def _load_state(self):
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"mappings": {}, "progress": {}}

    def _save_state(self):
        if not self.apply:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.state_path)

    def _storygraph_result(self, payload):
        result = json.loads(payload)
        if "error" in result:
            raise RuntimeError(result["error"])
        return result

    def _match(self, item):
        item_id = item["id"]
        existing = self.state["mappings"].get(item_id)
        if existing:
            return existing

        metadata = item.get("media", {}).get("metadata", {})
        identifiers = [metadata.get("isbn"), metadata.get("asin")]
        title = metadata.get("title")
        authors = metadata.get("authors") or []
        author_names = [a.get("name") if isinstance(a, dict) else a for a in authors]
        queries = [value for value in identifiers if value]
        queries.append(" ".join(value for value in (title, *author_names[:1]) if value))
        for query in queries:
            results = self._storygraph_result(self.storygraph.search(query))
            if len(results) == 1:
                match = results[0]
            else:
                ranked = sorted(
                    (
                        (_title_score(title, result.get("title")), result)
                        for result in results
                        if not author_names
                        or _normalized(result.get("author"))
                        == _normalized(author_names[0])
                    ),
                    key=lambda pair: pair[0],
                    reverse=True,
                )
                if not ranked or ranked[0][0] < 90:
                    continue
                if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
                    continue
                match = ranked[0][1]
            self.state["mappings"][item_id] = match["book_id"]
            return match["book_id"]
        return None

    def run(self):
        summary = {"updated": 0, "unchanged": 0, "unmatched": 0, "errors": 0}
        for progress in self.audiobookshelf.progress():
            try:
                if not progress.get("libraryItemId"):
                    continue
                item = self.audiobookshelf.item(progress["libraryItemId"])
                storygraph_id = self._match(item)
                if not storygraph_id:
                    LOG.warning(
                        "No unambiguous StoryGraph match for %s", item.get("id")
                    )
                    summary["unmatched"] += 1
                    continue
                percent = min(
                    100, max(0, round(float(progress.get("progress", 0)) * 100))
                )
                finished = (
                    bool(progress.get("isFinished")) or percent >= self.finish_threshold
                )
                if finished:
                    percent = 100
                previous = int(self.state["progress"].get(item["id"], 0))
                remote = self._storygraph_result(
                    self.storygraph.reading_progress(storygraph_id)
                )
                remote_percent = int(remote.get("progress_percent") or 0)
                floor = max(previous, remote_percent)
                if percent <= floor or (
                    not finished and percent - floor < self.minimum_change
                ):
                    summary["unchanged"] += 1
                    continue
                LOG.info(
                    "%s: %s -> %s%%%s",
                    "apply" if self.apply else "dry-run",
                    item.get("media", {}).get("metadata", {}).get("title", item["id"]),
                    percent,
                    " (finished)" if finished else "",
                )
                if self.apply:
                    status = (remote.get("status") or "").strip().casefold()
                    if not status or status in {"to read", "paused"}:
                        self._storygraph_result(
                            self.storygraph.update_status(
                                storygraph_id, "currently-reading"
                            )
                        )
                    self._storygraph_result(
                        self.storygraph.update_progress(storygraph_id, percent)
                    )
                    if finished and status != "read":
                        self._storygraph_result(
                            self.storygraph.update_status(storygraph_id, "read")
                        )
                    self.state["progress"][item["id"]] = percent
                summary["updated"] += 1
            except Exception as exc:
                LOG.error("Failed to sync %s: %s", progress.get("libraryItemId"), exc)
                summary["errors"] += 1
        self._save_state()
        return summary


def build_sync(args):
    required = {
        "AUDIOBOOKSHELF_URL": os.getenv("AUDIOBOOKSHELF_URL"),
        "AUDIOBOOKSHELF_TOKEN": os.getenv("AUDIOBOOKSHELF_TOKEN"),
        "STORYGRAPH_REMEMBER_TOKEN": os.getenv("STORYGRAPH_REMEMBER_TOKEN"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    cookies = {"remember_user_token": required["STORYGRAPH_REMEMBER_TOKEN"]}
    if os.getenv("STORYGRAPH_SESSION"):
        cookies["_storygraph_session"] = os.environ["STORYGRAPH_SESSION"]
    return ProgressSync(
        AudiobookshelfClient(
            required["AUDIOBOOKSHELF_URL"], required["AUDIOBOOKSHELF_TOKEN"]
        ),
        Book(cookies=cookies),
        args.state,
        apply=args.apply,
        minimum_change=args.minimum_change,
        finish_threshold=args.finish_threshold,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Sync Audiobookshelf listening progress to StoryGraph."
    )
    parser.add_argument("--apply", action="store_true", help="write changes")
    parser.add_argument("--loop", action="store_true", help="run continuously")
    parser.add_argument("--interval", type=int, default=900)
    parser.add_argument("--minimum-change", type=int, default=2)
    parser.add_argument("--finish-threshold", type=int, default=99)
    parser.add_argument("--state", default="/data/state.json")
    args = parser.parse_args(argv)
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    while True:
        summary = build_sync(args).run()
        LOG.info("Sync summary: %s", json.dumps(summary, sort_keys=True))
        if not args.loop:
            return 1 if summary["errors"] else 0
        time.sleep(max(60, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
