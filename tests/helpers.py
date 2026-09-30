from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from llm_handshake import Config
from llm_handshake.mock import completion, encode_stream, stream_chunks
from llm_handshake.sse import SSEParser
from llm_handshake.transport import WireResponse
from llm_handshake.validators import inspect

CONFIG = Config("https://example.test/v1", "handshake-demo")


def json_wire(data: Any) -> WireResponse:
    body = json.dumps(data).encode()
    return WireResponse(200, body=body, elapsed_ms=1.25, byte_count=len(body))


def stream_wire(parts=None, done=True) -> WireResponse:
    body = encode_stream(stream_chunks() if parts is None else parts, done)
    parser = SSEParser()
    events = parser.feed(body) + parser.finish()
    return WireResponse(200, events=[(event, float(i)) for i, event in enumerate(events)], byte_count=len(body))


def inspected(data=None, name="chat"):
    return inspect(name, json_wire(completion() if data is None else data), CONFIG)


def codes(result):
    return {f.code for f in result.findings}


@contextmanager
def endpoint(body=b'{"data":[]}', status=200, mime="application/json", headers=None,
             delay=0.0, drip=False, declared_length=None, omit_length=False, ssl_context=None):
    records = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def handle_request(self):
            length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(length) if length else b""
            records.append({"path": self.path, "method": self.command,
                            "authorization": self.headers.get("Authorization"), "body": payload})
            self.send_response(status)
            if mime is not None:
                self.send_header("Content-Type", mime)
            if not omit_length:
                self.send_header("Content-Length", str(len(body) if declared_length is None else declared_length))
            self.send_header("Connection", "close")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            try:
                if drip:
                    for byte in body:
                        time.sleep(delay)
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                else:
                    time.sleep(delay)
                    self.wfile.write(body)
                    self.wfile.flush()
            except (OSError, ValueError):
                pass
            self.close_connection = True

        do_GET = handle_request
        do_POST = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    if ssl_context:
        server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        scheme = "https" if ssl_context else "http"
        yield f"{scheme}://127.0.0.1:{server.server_port}/v1", records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
