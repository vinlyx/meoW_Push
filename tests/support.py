"""Test helpers: a local stand-in for the MeoW endpoint."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional


class MockMeoW:
    """Tiny HTTP server that records requests and replays a canned response."""

    def __init__(
        self,
        response: Optional[Dict[str, Any]] = None,
        *,
        status: int = 200,
        raw: Optional[bytes] = None,
    ) -> None:
        self.requests: List[Dict[str, Any]] = []
        self.response = (
            response
            if response is not None
            else {"status": 200, "data": True, "msg": "发送成功"}
        )
        self.status = status
        self.raw = raw
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                outer.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": dict(self.headers),
                        "body": body,
                    }
                )
                payload = outer.raw
                if payload is None:
                    payload = json.dumps(outer.response, ensure_ascii=False).encode("utf-8")
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: Any) -> None:  # keep test output clean
                return

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return "http://{0}:{1}".format(host, port)

    def __enter__(self) -> "MockMeoW":
        self._thread.start()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
