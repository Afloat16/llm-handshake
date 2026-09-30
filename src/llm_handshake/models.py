"""Stable report records. Raw response bodies and credentials never belong here."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA = "llm-handshake.report.v1"
SUITE_VERSION = 1
SEVERITY = {"pass": 0, "warn": 1, "fail": 2}


@dataclass
class Finding:
    status: str
    code: str
    message: str
    hint: str = ""
    path: str = ""


@dataclass
class ProbeResult:
    name: str
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, int | float | bool | None] = field(default_factory=dict)
    http_status: int | None = None
    requests: int = 1
    skipped: bool = False

    @property
    def status(self) -> str:
        if self.skipped:
            return "skip"
        return max((f.status for f in self.findings), key=SEVERITY.__getitem__, default="pass")

    def add(self, status: str, code: str, message: str, hint: str = "", path: str = "") -> None:
        if status not in SEVERITY:
            raise ValueError("Unknown finding status.")
        self.findings.append(Finding(status, code, message, hint, path))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("skipped")
        d["status"] = self.status
        return d


def skipped(name: str, message: str) -> ProbeResult:
    r = ProbeResult(name, requests=0, skipped=True)
    r.add("warn", "not_run", message, "Resolve the preceding error, then rerun this probe.")
    return r
