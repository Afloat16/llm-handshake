"""Incremental SSE framing based on WHATWG HTML §9.2 (see docs/REFERENCES.md).

This is a diagnostic parser, not a reconnecting EventSource client. Incomplete
frames at EOF are discarded. CR, LF, CRLF, UTF-8 splits, and multiline data work.
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass


class StreamError(ValueError):
    """Malformed or oversized stream; messages contain no response data."""


@dataclass(frozen=True)
class Event:
    data: str
    event: str = "message"


class SSEParser:
    def __init__(self, max_chars: int = 262_144) -> None:
        self.max_chars = max_chars
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._line: list[str] = []
        self._data: list[str] = []
        self._event = ""
        self._size = 0
        self._skip_lf = False
        self._start = True
        self._closed = False

    @property
    def pending(self) -> bool:
        return bool(self._line or self._data)

    def _end_line(self) -> Event | None:
        line = "".join(self._line)
        self._line.clear()
        if not line:
            out = Event("\n".join(self._data), self._event or "message") if self._data else None
            self._data.clear()
            self._event = ""
            self._size = 0
            return out
        if line.startswith(":"):
            return None
        key, sep, value = line.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if key == "data":
            self._data.append(value)
            self._size += len(value) + 1
        elif key == "event":
            self._event = value
        if self._size > self.max_chars:
            raise StreamError("SSE event exceeded its character limit.")
        return None

    def _consume(self, text: str) -> list[Event]:
        events: list[Event] = []
        for char in text:
            if self._start:
                self._start = False
                if char == "\ufeff":
                    continue
            if self._skip_lf:
                self._skip_lf = False
                if char == "\n":
                    continue
            if char in ("\r", "\n"):
                event = self._end_line()
                if event is not None:
                    events.append(event)
                self._skip_lf = char == "\r"
            else:
                self._line.append(char)
                if len(self._line) + self._size > self.max_chars:
                    raise StreamError("SSE event exceeded its character limit.")
        return events

    def feed(self, chunk: bytes) -> list[Event]:
        if self._closed:
            raise StreamError("Cannot feed a closed SSE parser.")
        try:
            text = self._decoder.decode(chunk)
        except UnicodeError:
            raise StreamError("SSE response is not valid UTF-8.") from None
        return self._consume(text)

    def finish(self) -> list[Event]:
        if self._closed:
            return []
        self._closed = True
        try:
            text = self._decoder.decode(b"", final=True)
        except UnicodeError:
            raise StreamError("SSE response ended inside a UTF-8 sequence.") from None
        # Deliberately do not dispatch a data buffer without a final blank line.
        return self._consume(text)
