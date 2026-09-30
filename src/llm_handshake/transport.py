"""Bounded direct HTTP transport. No redirects, retries, proxies, or body logs."""
from __future__ import annotations

import http.client
import json
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from . import __version__
from .config import Config
from .plan import RequestSpec
from .sse import Event, SSEParser, StreamError


class TransportError(Exception):
    def __init__(self, code: str, http_status: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.http_status = http_status


@dataclass
class WireResponse:
    status: int
    body: bytes = b""
    events: list[tuple[Event, float]] = field(default_factory=list)
    elapsed_ms: float = 0.0
    byte_count: int = 0


class Transport:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._url = urlsplit(config.base_url)
        # Build the context before any request so bad CA configuration sends nothing.
        try:
            self._ssl = ssl.create_default_context()
            if config.ca_file:
                self._ssl.load_verify_locations(cafile=config.ca_file)
        except (OSError, ssl.SSLError):
            raise ValueError("Could not load the CA bundle. Check --ca-file.") from None

    def request(self, spec: RequestSpec) -> WireResponse:
        config = self.config
        started = time.monotonic()
        kwargs = {"host": self._url.hostname, "port": self._url.port, "timeout": config.timeout}
        if self._url.scheme == "https":
            conn = http.client.HTTPSConnection(**kwargs, context=self._ssl)
        else:
            conn = http.client.HTTPConnection(**kwargs)
        expired = threading.Event()
        wire_socket = None
        response = None

        def expire() -> None:
            expired.set()
            sock = conn.sock or wire_socket
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

        timer = threading.Timer(config.timeout, expire)
        timer.daemon = True
        timer.start()
        headers = {
            "User-Agent": "llm-handshake/" + __version__,
            "Accept": "text/event-stream" if spec.streaming else "application/json",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        if config.api_key:
            headers["Authorization"] = "Bearer " + config.api_key
        payload = None
        if spec.payload is not None:
            payload = json.dumps(spec.payload, separators=(",", ":"), allow_nan=False).encode()
            headers["Content-Type"] = "application/json"
        status: int | None = None
        try:
            conn.request(spec.method, self._url.path + spec.path, body=payload, headers=headers)
            wire_socket = conn.sock
            if expired.is_set():
                raise TransportError("timeout")
            response = conn.getresponse()
            status = response.status
            if not 200 <= status < 300:
                # Do not read or retain error bodies. They may echo credentials.
                raise TransportError("http_status", status)
            encoding = response.getheader("Content-Encoding", "identity").lower().strip()
            if encoding not in ("", "identity"):
                raise TransportError("content_encoding", status)
            mime = response.getheader("Content-Type", "").split(";", 1)[0].lower().strip()
            expected = "text/event-stream" if spec.streaming else "application/json"
            if mime != expected and not (not spec.streaming and mime.startswith("application/") and mime.endswith("+json")):
                raise TransportError("content_type", status)
            length = response.getheader("Content-Length")
            size = None
            if length is not None:
                try:
                    size = int(length)
                except ValueError:
                    raise TransportError("invalid_content_length", status) from None
                if size < 0:
                    raise TransportError("invalid_content_length", status)
                if size > config.max_response_bytes:
                    raise TransportError("response_limit", status)
            result = WireResponse(status)
            body = bytearray()
            parser = SSEParser(min(config.max_response_bytes, 262_144)) if spec.streaming else None
            while True:
                remaining = config.timeout - (time.monotonic() - started)
                if expired.is_set() or remaining <= 0:
                    raise TransportError("timeout", status)
                if wire_socket is not None and wire_socket.fileno() != -1:
                    wire_socket.settimeout(remaining)
                chunk = response.read1(min(4096, config.max_response_bytes - result.byte_count + 1))
                if expired.is_set():
                    raise TransportError("timeout", status)
                if not chunk:
                    if parser is not None:
                        for event in parser.finish():
                            result.events.append((event, (time.monotonic() - started) * 1000))
                    break
                result.byte_count += len(chunk)
                if result.byte_count > config.max_response_bytes:
                    raise TransportError("response_limit", status)
                if parser is None:
                    body.extend(chunk)
                else:
                    events = parser.feed(chunk)
                    elapsed = (time.monotonic() - started) * 1000
                    result.events.extend((event, elapsed) for event in events)
                    if len(result.events) > 4096:
                        raise TransportError("event_limit", status)
                    if any(event.data == "[DONE]" for event in events):
                        break
            if parser is None and size is not None and result.byte_count != size:
                raise TransportError("truncated_body", status)
            result.body = bytes(body)
            result.elapsed_ms = round((time.monotonic() - started) * 1000, 3)
            return result
        except TransportError:
            raise
        except (socket.timeout, TimeoutError):
            raise TransportError("timeout", status) from None
        except ssl.SSLError:
            raise TransportError("tls_error", status) from None
        except StreamError:
            raise TransportError("sse_framing", status) from None
        except (OSError, http.client.HTTPException, UnicodeError, ValueError):
            raise TransportError("timeout" if expired.is_set() else "connection_error", status) from None
        finally:
            timer.cancel()
            if response is not None:
                response.close()
            conn.close()
