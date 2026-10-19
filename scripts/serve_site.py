"""Serve a built site the way GitHub Pages does: Python's http.server, with text files sent gzip-compressed when the
browser accepts it (Pages compresses HTML, CSS, JavaScript, JSON, SVG and XML). Lighthouse (.github/workflows/lighthouse.yml)
then measures the bytes a reader is sent, not an uncompressed copy no host serves.

    python scripts/serve_site.py <dir> <port>        (binds 127.0.0.1)
"""
from __future__ import annotations

import functools
import gzip
import http.server
import io
import os
import sys

TEXT = {".html", ".css", ".js", ".mjs", ".json", ".svg", ".xml", ".atom", ".txt", ".map", ".webmanifest", ".md"}


class Handler(http.server.SimpleHTTPRequestHandler):
    _cache: dict[tuple[str, float], bytes] = {}

    def send_head(self):  # noqa: D401 - http.server's own hook
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            if not self.path.split("?", 1)[0].endswith("/"):
                return super().send_head()                      # the redirect to the slash, as http.server does it
            path = os.path.join(path, "index.html")
        ext = os.path.splitext(path)[1].lower()
        if ext not in TEXT or "gzip" not in self.headers.get("Accept-Encoding", "") or not os.path.isfile(path):
            return super().send_head()
        key = (path, os.path.getmtime(path))
        body = self._cache.get(key)
        if body is None:
            with open(path, "rb") as f:
                body = self._cache[key] = gzip.compress(f.read(), compresslevel=6, mtime=0)
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        return io.BytesIO(body)

    def log_message(self, *args):  # quiet, like Pages
        pass


def main(argv: list[str]) -> None:
    root, port = argv[1], int(argv[2])
    http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=root)).serve_forever()


if __name__ == "__main__":
    main(sys.argv)
