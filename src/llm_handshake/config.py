"""Configuration validation. No network I/O or environment reads at import time."""
from __future__ import annotations

import hashlib
import ipaddress
import math
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

PROBES = ("models", "chat", "stream", "stream-usage", "tools", "tool-stream", "json")


def normalize_url(value: str, allow_http: bool = False) -> str:
    if not isinstance(value, str) or not value or not value.isascii():
        raise ValueError("Use an ASCII HTTP(S) API base URL; percent-encode non-ASCII paths.")
    if any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
        raise ValueError("The base URL must not contain whitespace, controls, or backslashes.")
    try:
        u = urlsplit(value)
        port = u.port
        host = u.hostname
    except ValueError:
        raise ValueError("The base URL has an invalid host or port.") from None
    if u.scheme not in ("http", "https") or not host:
        raise ValueError("Use an absolute http:// or https:// API base URL.")
    if u.username is not None or u.password is not None or "?" in value or "#" in value:
        raise ValueError("Credentials, query strings, and fragments are not allowed in the base URL.")
    if port == 0:
        raise ValueError("The URL port must be between 1 and 65535.")
    # Older urllib versions accept bracketed non-IP hostnames. Validate the
    # authority ourselves so every supported interpreter enforces the same rule.
    if "[" in u.netloc or "]" in u.netloc:
        if not re.fullmatch(r"\[[^\[\]]+\](?::[0-9]+)?", u.netloc):
            raise ValueError("Bracketed hosts must use a valid IPv6 authority.")
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            raise ValueError("Bracketed hosts must be valid IPv6 addresses.") from None
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", host):
            raise ValueError("The base URL contains an invalid hostname.") from None
        loopback = host.lower() == "localhost"
    if u.scheme == "http" and not loopback and not allow_http:
        raise ValueError("Remote plaintext HTTP is disabled. Use HTTPS or explicitly pass --allow-http.")
    path = u.path.rstrip("/")
    if re.search(r"%0[ad]", path, re.I):
        raise ValueError("Encoded line breaks are not allowed in the URL.")
    if path.endswith(("/chat/completions", "/models", "/responses")):
        raise ValueError("Use the API base URL (for example /v1), not a complete endpoint route.")
    return urlunsplit((u.scheme, u.netloc.lower(), path, "", ""))


def select_probes(value: str) -> tuple[str, ...]:
    if value == "all":
        return PROBES
    parts = tuple(p.strip() for p in value.split(","))
    if not parts or any(p not in PROBES for p in parts):
        raise ValueError("Unknown probe. Choose: " + ", ".join(PROBES) + ", or all.")
    if len(parts) != len(set(parts)):
        raise ValueError("Probe names must not be repeated.")
    # Canonical order makes plans and comparisons reproducible.
    return tuple(p for p in PROBES if p in parts)


@dataclass(frozen=True)
class Config:
    base_url: str = field(repr=False)
    model: str = ""
    api_key: str = field(default="", repr=False)
    probes: tuple[str, ...] = ("models",)
    allow_inference: bool = False
    allow_http: bool = False
    timeout: float = 20.0
    max_output_tokens: int = 128
    token_limit_field: str = "max_tokens"
    max_requests: int = 7
    max_response_bytes: int = 1_048_576
    ca_file: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", normalize_url(self.base_url, self.allow_http))
        if not isinstance(self.model, str) or len(self.model) > 256 or any(
            ord(c) < 32 or ord(c) == 127 for c in self.model
        ):
            raise ValueError("Model identifiers must be strings of at most 256 characters without controls.")
        if not isinstance(self.api_key, str) or len(self.api_key) > 8192 or (
            self.api_key and not re.fullmatch(r"[!-~]+", self.api_key)
        ):
            raise ValueError("The API key must be a printable ASCII token without whitespace.")
        if not isinstance(self.probes, tuple) or not self.probes or any(p not in PROBES for p in self.probes):
            raise ValueError("Select at least one known probe as a tuple.")
        if len(self.probes) != len(set(self.probes)):
            raise ValueError("Probe names must not be repeated.")
        object.__setattr__(self, "probes", tuple(p for p in PROBES if p in self.probes))
        if any(p != "models" for p in self.probes) and not self.model.strip():
            raise ValueError("A model is required for inference probes; set --model or OPENAI_MODEL.")
        if isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float)) or not (
            math.isfinite(self.timeout) and 0 < self.timeout <= 300
        ):
            raise ValueError("Timeout must be finite, greater than zero, and at most 300 seconds.")
        for name, low, high in (
            ("max_output_tokens", 1, 4096),
            ("max_requests", 1, 32),
            ("max_response_bytes", 128, 8_388_608),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer between {low} and {high}.")
        if self.token_limit_field not in ("max_tokens", "max_completion_tokens"):
            raise ValueError("Use max_tokens or max_completion_tokens for the token limit field.")
        if len(self.probes) > self.max_requests:
            raise ValueError("The selected plan exceeds --max-requests; no requests were sent.")

    @property
    def origin(self) -> str:
        u = urlsplit(self.base_url)
        return urlunsplit((u.scheme, u.netloc, "", "", ""))

    @property
    def target_id(self) -> str:
        return hashlib.sha256((self.base_url + "\n" + self.model).encode()).hexdigest()
