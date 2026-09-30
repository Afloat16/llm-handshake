"""Loopback-only demonstration server with deterministic, synthetic responses."""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from typing import Any, Iterator


class _LoopbackHTTPServer(ThreadingHTTPServer):
    """Fixed-address local fixtures do not need reverse DNS during binding."""

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


USAGE = {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}


def completion(content: str = "READY", *, tool: bool = False) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool:
        message["content"] = None
        message["tool_calls"] = [{"id": "call_demo", "type": "function", "function": {
            "name": "handshake_echo", "arguments": '{"value":7}',
        }}]
    return {"id": "chatcmpl-demo", "object": "chat.completion", "created": 1_700_000_000,
            "model": "handshake-demo", "choices": [{"index": 0, "message": message,
            "finish_reason": "tool_calls" if tool else "stop"}], "usage": dict(USAGE)}


def chunk(delta: dict[str, Any] | None = None, finish: str | None = None,
          *, usage_only: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": "chatcmpl-demo", "object": "chat.completion.chunk", "created": 1_700_000_000,
        "model": "handshake-demo", "choices": [] if usage_only else [{
            "index": 0, "delta": delta or {}, "finish_reason": finish,
        }],
    }
    if usage_only:
        result["usage"] = dict(USAGE)
    return result


def stream_chunks(tool: bool = False, include_usage: bool = False,
                  broken: bool = False) -> list[dict[str, Any]]:
    parts = [chunk({"role": "assistant"})]
    if tool:
        parts.append(chunk({"tool_calls": [{"index": 0, "id": "call_demo", "type": "function",
                     "function": {"name": "handshake_echo", "arguments": '{"val'}}]}))
        parts.append(chunk({"tool_calls": [{"index": 0, "function": {"arguments": 'ue":'}}]}))
        parts.append(chunk({"tool_calls": [{"index": 0, "function": {"arguments": '"7"}' if broken else '7}'}}]}))
    else:
        parts.extend([chunk({"content": "REA"}), chunk({"content": "DY ✓"})])
    parts.append(chunk(finish="tool_calls" if tool else "stop"))
    if include_usage and not broken:
        parts.append(chunk(usage_only=True))
    return parts


def encode_stream(parts: list[dict[str, Any]], done: bool = True) -> bytes:
    frames = [": handshake keepalive\r\n\r\n"]
    frames.extend("data: " + json.dumps(part, ensure_ascii=False) + "\r\n\r\n" for part in parts)
    if done:
        frames.append("data: [DONE]\r\n\r\n")
    return "".join(frames).encode("utf-8")


@contextmanager
def mock_server(broken: bool = False) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def send_data(self, data: bytes, mime: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                if mime == "text/event-stream":
                    for i in range(0, len(data), 17):
                        self.wfile.write(data[i:i + 17])
                        self.wfile.flush()
                else:
                    self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True

        def send_json(self, data: Any, status: int = 200) -> None:
            self.send_data(json.dumps(data).encode(), "application/json", status)

        def do_GET(self) -> None:
            if self.path != "/v1/models":
                self.send_json({"error": "not found"}, 404)
                return
            self.send_json({"object": "list", "data": [{"id": "handshake-demo", "object": "model"}]})

        def do_POST(self) -> None:
            if self.path != "/v1/chat/completions":
                self.send_json({"error": "not found"}, 404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65_536:
                    raise ValueError
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError
            except (ValueError, UnicodeError):
                self.send_json({"error": "invalid request"}, 400)
                return
            tool = bool(payload.get("tools"))
            if payload.get("stream"):
                data = encode_stream(stream_chunks(tool, bool(payload.get("stream_options")), broken))
                self.send_data(data, "text/event-stream")
            else:
                content = '{"value":"7"}' if broken else '{"value":7}'
                self.send_json(completion(content if payload.get("response_format") else "READY", tool=tool))

    server = _LoopbackHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
