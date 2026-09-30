"""Machine-readable reports, safe rendering, and conservative regression gates."""
from __future__ import annotations

import html
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from .config import PROBES
from .models import SCHEMA
from .validators import load_json


def clean_text(value: str) -> str:
    return "".join(c for c in value if unicodedata.category(c) not in ("Cc", "Cf", "Cs"))


def scrub(value: Any, secret: str = "") -> Any:
    if isinstance(value, str):
        return clean_text(value.replace(secret, "[REDACTED]") if secret else value)
    if isinstance(value, list):
        return [scrub(item, secret) for item in value]
    if isinstance(value, dict):
        # Keys are fixed schema keys, not provider data. Preserve them even for short keys.
        return {key: scrub(item, secret) for key, item in value.items()}
    return value


def gate(report: dict[str, Any], strict: bool = False, required: tuple[str, ...] = ()) -> int:
    if any(name not in PROBES for name in required):
        raise ValueError("Unknown required probe.")
    statuses = {r["name"]: r["status"] for r in report["results"]}
    if any(statuses.get(name) != "pass" for name in required):
        return 1
    if any(status == "fail" or (strict and status != "pass") for status in statuses.values()):
        return 1
    return 0


def _escape(value: Any) -> str:
    return html.escape(clean_text(str(value)), quote=False).replace("|", "\\|").replace("`", "&#96;")


def render(report: dict[str, Any], format: str = "text") -> str:
    report = scrub(report)
    if format == "json":
        return json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if format not in ("text", "markdown"):
        raise ValueError("Choose text, json, or markdown output.")
    summary = report["summary"]
    counts = " / ".join(f"{summary[s]} {s}" for s in ("pass", "warn", "fail", "skip"))
    if format == "markdown":
        lines = ["# LLM Handshake", "", f"**{counts}** · {report['requests_attempted']} requests", "",
                 "| Probe | Result | Observation |", "| :--- | :--- | :--- |"]
        for result in report["results"]:
            observations = "; ".join(f["message"] for f in result["findings"] if f["status"] != "pass")
            if not observations:
                observations = "The selected sample passed its checks."
            lines.append(f"| {_escape(result['name'])} | {result['status'].upper()} | {_escape(observations)} |")
        lines += ["", "## Next steps", ""]
        hints = list(dict.fromkeys(f["hint"] for r in report["results"] for f in r["findings"] if f["hint"]))
        lines += [f"- {_escape(hint)}" for hint in hints] or ["No corrective action was identified by these samples."]
        lines += ["", "## Scope", "", "One synthetic sample per probe, not a certification or billing estimate.",
                  "No credentials, response bodies, model-list entries, or full URL paths are included.",
                  "The JSON report contains the endpoint origin and selected model; review before sharing."]
        return "\n".join(lines) + "\n"
    lines = ["LLM Handshake", "=" * 60, counts,
             f"Requests: {report['requests_attempted']} ({report['inference_requests_attempted']} inference)", ""]
    for result in report["results"]:
        duration = result["metrics"].get("duration_ms")
        timing = f"  {duration:.1f} ms" if isinstance(duration, (int, float)) else ""
        lines.append(f"{result['status'].upper():4}  {result['name']:<14}{timing}")
        for finding in result["findings"]:
            if finding["status"] != "pass":
                lines.append(f"      [{finding['code']}] {finding['message']}")
                if finding["hint"]:
                    lines.append("      Try: " + finding["hint"])
    lines += ["", "One sample per probe. Not a certification or a monetary cost cap."]
    return "\n".join(lines) + "\n"


def write_private(path: str | Path, content: str) -> None:
    destination = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".handshake-", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, destination)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_report(path: str | Path) -> dict[str, Any]:
    with open(path, "rb") as stream:
        payload = stream.read(2_097_153)
    if len(payload) > 2_097_152:
        raise ValueError("Report exceeds the 2 MiB input limit.")
    try:
        data = load_json(payload)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("Report is not valid bounded UTF-8 JSON.") from None
    validate_report(data)
    return data


def validate_report(data: Any) -> None:
    """Validate the comparison boundary, not arbitrary provider response objects."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("Unsupported report schema; use a llm-handshake.report.v1 report.")
    target = data.get("target")
    contract = data.get("contract")
    if not isinstance(target, dict) or not isinstance(target.get("id"), str) or not re.fullmatch(r"[a-f0-9]{64}", target["id"]):
        raise ValueError("Report has an invalid target fingerprint.")
    if not isinstance(contract, dict) or set(contract) != {"suite_version", "max_output_tokens", "token_limit_field"}:
        raise ValueError("Report has an invalid probe contract.")
    if type(contract["suite_version"]) is not int or contract["suite_version"] < 1:
        raise ValueError("Report has an invalid suite version.")
    if type(contract["max_output_tokens"]) is not int or not 1 <= contract["max_output_tokens"] <= 4096:
        raise ValueError("Report has an invalid output limit.")
    if contract["token_limit_field"] not in ("max_tokens", "max_completion_tokens"):
        raise ValueError("Report has an invalid token limit field.")
    results = data.get("results")
    if not isinstance(results, list) or not 1 <= len(results) <= len(PROBES):
        raise ValueError("Report needs a bounded, nonempty results array.")
    names: set[str] = set()
    for result in results:
        if not isinstance(result, dict) or result.get("name") not in PROBES or result.get("status") not in ("pass", "warn", "fail", "skip"):
            raise ValueError("Report contains an invalid probe or status.")
        if result["name"] in names:
            raise ValueError("Report contains duplicate probe names.")
        names.add(result["name"])


def compare(before: dict[str, Any], after: dict[str, Any], allow_target_change: bool = False) -> dict[str, Any]:
    validate_report(before)
    validate_report(after)
    if before["contract"] != after["contract"]:
        raise ValueError("Probe contracts differ. Rerun the baseline with the same suite version and token settings.")
    same_target = before["target"]["id"] == after["target"]["id"]
    if not same_target and not allow_target_change:
        raise ValueError("Targets differ. Use --allow-target-change only for an intentional cross-target comparison.")
    old = {r["name"]: r["status"] for r in before["results"]}
    new = {r["name"]: r["status"] for r in after["results"]}
    rank = {"pass": 3, "warn": 2, "fail": 1, "skip": 0, "missing": -1}
    changes = []
    for name in PROBES:
        left, right = old.get(name, "missing"), new.get(name, "missing")
        if left == right:
            continue
        if name not in old:
            kind = "added"
        elif name not in new or rank[right] < rank[left]:
            kind = "regression"
        else:
            kind = "improvement"
        changes.append({"probe": name, "before": left, "after": right, "kind": kind})
    return {"schema": "llm-handshake.comparison.v1", "same_target": same_target,
            "regressions": sum(c["kind"] == "regression" for c in changes), "changes": changes}


def render_comparison(data: dict[str, Any], format: str = "text") -> str:
    if format == "json":
        return json.dumps(data, indent=2) + "\n"
    lines = ["# LLM Handshake comparison" if format == "markdown" else "LLM Handshake comparison",
             f"Regressions: {data['regressions']}"]
    if not data["same_target"]:
        lines.append("Intentional cross-target comparison; targets differ.")
    for change in data["changes"]:
        lines.append(f"{change['kind'].upper()}: {change['probe']}  {change['before']} -> {change['after']}")
    if not data["changes"]:
        lines.append("No probe-status changes observed. Timing and usage are not regression gates.")
    return "\n\n".join(lines) + "\n"
