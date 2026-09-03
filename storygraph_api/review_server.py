from __future__ import annotations

import base64
import html
import os
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse


def _escape(value):
    return html.escape(str(value or ""), quote=True)


def _layout(sync, csrf_token, notice=""):
    with sync.lock:
        unmatched = list(sync.state["unmatched"].values())
        ignored = list(sync.state["ignored"].values())
        mappings = dict(sync.state["mappings"])

    cards = []
    for review in sorted(unmatched, key=lambda row: row["item"]["title"].casefold()):
        item = review["item"]
        item_id = _escape(item["id"])
        candidates = []
        for index, candidate in enumerate(review["candidates"]):
            book_id = _escape(candidate["book_id"])
            checked = " checked" if index == 0 else ""
            candidates.append(
                f"""
                <label class="candidate">
                  <input type="radio" name="storygraph_id" value="{book_id}"{checked}>
                  <span><strong>{_escape(candidate["title"])}</strong>
                    <span class="meta">by {_escape(candidate.get("author") or "Unknown author")}</span>
                    <span class="reason">{_escape(candidate["reason"])} · confidence {candidate["score"]}/100</span>
                    <a href="https://app.thestorygraph.com/books/{book_id}" target="_blank" rel="noreferrer">View edition<span class="sr-only"> of {_escape(candidate["title"])}</span></a>
                  </span>
                </label>"""
            )
        choice = "".join(candidates) or (
            '<p class="empty">No candidates found. Search StoryGraph manually, then '
            "use Search again after improving Audiobookshelf metadata.</p>"
        )
        confirm = (
            '<button type="submit">Confirm selected match</button>'
            if candidates
            else ""
        )
        cards.append(
            f"""
            <article class="card">
              <header><div><h2>{_escape(item["title"])}</h2>
                <p>{_escape(item.get("author") or "Unknown author")}</p></div>
                <img src="/cover/{item_id}" alt="" loading="lazy">
              </header>
              <form method="post" action="/confirm">
                <input type="hidden" name="csrf" value="{csrf_token}">
                <input type="hidden" name="item_id" value="{item_id}">
                <fieldset><legend>Possible StoryGraph editions</legend>{choice}</fieldset>
                <div class="actions">{confirm}</div>
              </form>
              <div class="secondary-actions">
                <form method="post" action="/retry"><input type="hidden" name="csrf" value="{csrf_token}"><input type="hidden" name="item_id" value="{item_id}"><button class="secondary">Search again</button></form>
                <form method="post" action="/ignore"><input type="hidden" name="csrf" value="{csrf_token}"><input type="hidden" name="item_id" value="{item_id}"><button class="quiet">Ignore permanently</button></form>
              </div>
            </article>"""
        )

    ignored_rows = (
        "".join(
            f'<li><span><strong>{_escape(item["title"])}</strong> · {_escape(item.get("author") or "Unknown author")}</span><form method="post" action="/retry"><input type="hidden" name="csrf" value="{csrf_token}"><input type="hidden" name="item_id" value="{_escape(item["id"])}"><button class="secondary">Review again</button></form></li>'
            for item in ignored
        )
        or "<li>Nothing ignored.</li>"
    )
    mapping_rows = (
        "".join(
            f'<li><code>{_escape(item_id)}</code> → <a href="https://app.thestorygraph.com/books/{_escape(book_id)}">StoryGraph edition</a><form method="post" action="/undo"><input type="hidden" name="csrf" value="{csrf_token}"><input type="hidden" name="item_id" value="{_escape(item_id)}"><button class="quiet">Undo</button></form></li>'
            for item_id, book_id in sorted(mappings.items())
        )
        or "<li>No confirmed mappings yet.</li>"
    )
    notice_html = (
        f'<p class="notice" role="status">{_escape(notice)}</p>' if notice else ""
    )
    cards_html = "".join(cards) or (
        '<div class="all-clear"><h2>All clear</h2><p>No books need your attention.</p></div>'
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>StoryGraph match review</title><style>
:root{{--ink:#182018;--muted:#5d685d;--paper:#f7f3e8;--card:#fffdf7;--accent:#176b52;--line:#d8d3c5}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,sans-serif}}main{{width:min(880px,calc(100% - 2rem));margin:3rem auto}}h1{{font:700 clamp(2rem,6vw,4rem)/1.05 Georgia,serif;margin:.2rem 0}}.lede,.meta,.reason{{color:var(--muted)}}.count{{display:inline-block;background:#dceadf;color:#174b39;padding:.2rem .65rem;border-radius:999px;font-weight:700}}.notice,.all-clear{{padding:1rem;border:2px solid var(--accent);background:var(--card);border-radius:.75rem}}.card{{background:var(--card);border:1px solid var(--line);border-radius:1rem;padding:1.25rem;margin:1.25rem 0;box-shadow:0 8px 24px #3a43200d}}.card header{{display:flex;justify-content:space-between;gap:1rem}}.card h2{{margin:0;font-family:Georgia,serif}}.card header p{{margin:.2rem 0}}.card img{{width:64px;height:96px;object-fit:cover;border-radius:.3rem;background:#e5e0d4}}fieldset{{border:0;padding:0;margin:1rem 0}}legend{{font-weight:700;margin-bottom:.5rem}}.candidate{{display:grid;grid-template-columns:auto 1fr;gap:.7rem;padding:.85rem;margin:.55rem 0;border:1px solid var(--line);border-radius:.6rem;cursor:pointer}}.candidate:has(input:checked){{border-color:var(--accent);box-shadow:0 0 0 2px #176b5222}}.candidate span span,.candidate a{{display:block}}input[type=radio]{{margin-top:.35rem}}button{{border:0;border-radius:.45rem;padding:.65rem .9rem;background:var(--accent);color:white;font:inherit;font-weight:700;cursor:pointer}}button.secondary{{background:#e1e8df;color:#174b39}}button.quiet{{background:transparent;color:#8a342b;text-decoration:underline}}button:focus-visible,a:focus-visible,input:focus-visible{{outline:3px solid #d78e00;outline-offset:3px}}.secondary-actions,.actions,details li{{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}}details{{margin:2rem 0;border-top:1px solid var(--line);padding-top:1rem}}details li{{justify-content:space-between;padding:.5rem 0}}code{{overflow-wrap:anywhere}}.sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}@media(prefers-reduced-motion:reduce){{*{{scroll-behavior:auto!important}}}}
</style></head><body><main><p class="count">{len(unmatched)} need review</p><h1>Match your listening</h1><p class="lede">Choose the StoryGraph edition once. The sync remembers it from then on.</p>{notice_html}{cards_html}
<details><summary>Ignored books ({len(ignored)})</summary><ul>{ignored_rows}</ul></details>
<details><summary>Confirmed mappings ({len(mappings)})</summary><ul>{mapping_rows}</ul></details>
</main></body></html>"""


def start_review_server(sync, port):
    username = os.getenv("MATCH_REVIEW_USERNAME")
    password = os.getenv("MATCH_REVIEW_PASSWORD")
    if not username or not password:
        raise SystemExit(
            "MATCH_REVIEW_USERNAME and MATCH_REVIEW_PASSWORD are required with --review-port"
        )
    csrf_token = secrets.token_urlsafe(32)
    expected_auth = (
        "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
    )

    class ReviewHandler(BaseHTTPRequestHandler):
        def _authorized(self):
            supplied = self.headers.get("Authorization", "")
            return secrets.compare_digest(supplied, expected_auth)

        def _require_auth(self):
            if self._authorized():
                return True
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header(
                "WWW-Authenticate", 'Basic realm="StoryGraph match review"'
            )
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False

        def _send_html(self, status=HTTPStatus.OK, notice=""):
            body = _layout(sync, csrf_token, notice).encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'unsafe-inline'; img-src 'self'; form-action 'self'; frame-ancestors 'none'",
            )
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._require_auth():
                return
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_html()
                return
            if parsed.path.startswith("/cover/"):
                item_id = parsed.path.removeprefix("/cover/")
                with sync.lock:
                    known = item_id in sync.state["unmatched"]
                if not known:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                try:
                    response = sync.audiobookshelf.cover(item_id)
                    body = response.content
                    self.send_response(HTTPStatus.OK)
                    self.send_header(
                        "Content-Type",
                        response.headers.get("Content-Type", "image/jpeg"),
                    )
                    self.send_header("Cache-Control", "private, max-age=3600")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except Exception:
                    self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self):
            if not self._require_auth():
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length > 8192:
                self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            form = parse_qs(self.rfile.read(length).decode())
            if not secrets.compare_digest(form.get("csrf", [""])[0], csrf_token):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            item_id = form.get("item_id", [""])[0]
            actions = {
                "/confirm": lambda: sync.confirm_match(
                    item_id, form.get("storygraph_id", [""])[0]
                ),
                "/ignore": lambda: sync.ignore_match(item_id),
                "/retry": lambda: sync.retry_match(item_id),
                "/undo": lambda: sync.undo_match(item_id),
            }
            action = actions.get(urlparse(self.path).path)
            if action is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                action()
            except ValueError as exc:
                self._send_html(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, fmt, *args):
            return

    server = ThreadingHTTPServer(("0.0.0.0", port), ReviewHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server
