"""Run a validated, consented plan once. No implicit retries or fallbacks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import __version__
from .config import Config
from .models import ProbeResult, SCHEMA, skipped
from .plan import contract, make_plan
from .transport import Transport, TransportError
from .validators import inspect

ERRORS = {
    "truncated_body": ("The JSON body ended before its declared length.", "Inspect proxy truncation and HTTP response framing."),
    "timeout": ("The request exceeded its timeout.", "Check connectivity or explicitly increase --timeout."),
    "tls_error": ("TLS certificate validation or negotiation failed.", "Use a trusted endpoint or supply a valid --ca-file; verification stays enabled."),
    "connection_error": ("The connection failed or ended unexpectedly.", "Check the host, port, DNS, firewall, and server. Proxy environment variables are not used."),
    "content_type": ("The response Content-Type did not match the requested protocol.", "Check the base URL and whether a gateway buffered SSE into JSON or returned HTML."),
    "content_encoding": ("The server ignored the identity encoding request.", "Disable response compression on the diagnostic route; compressed bodies are not accepted."),
    "response_limit": ("The response exceeded the configured byte limit.", "Investigate the response size before increasing --max-response-bytes."),
    "event_limit": ("The stream exceeded 4096 events.", "Check for an unbounded or unexpectedly verbose stream."),
    "sse_framing": ("The stream contained invalid UTF-8 or an oversized SSE event.", "Check UTF-8 encoding and SSE framing at the gateway."),
    "invalid_content_length": ("The server sent an invalid Content-Length.", "Check HTTP response framing at the gateway."),
}


def failure(name: str, error: TransportError) -> ProbeResult:
    r = ProbeResult(name, http_status=error.http_status)
    status = error.http_status
    severity = "fail"
    code = error.code
    if code != "http_status":
        message, hint = ERRORS.get(code, ("The request could not be completed.", "Inspect the endpoint configuration."))
    elif status in (401, 403):
        code, message, hint = "authentication", "The endpoint rejected authentication or authorization.", "Check the API-key environment variable, account permissions, and selected model access."
    elif status == 429:
        code, message, hint = "rate_limited", "The endpoint rate-limited the request or rejected quota.", "Check quota and rate limits; no retries were attempted."
    elif status is not None and 300 <= status < 400:
        code, message, hint = "redirect_blocked", "The endpoint returned a redirect; it was not followed.", "Use the final trusted API base URL. Credentials are never forwarded to redirect targets."
    elif status == 404 and name == "models":
        severity = "warn"
        code, message, hint = "models_unavailable", "The model-list route returned HTTP 404.", "A missing model catalog does not prove chat is unavailable. Select an explicit inference probe."
    elif status == 404:
        code, message, hint = "route_or_model_missing", "The route or selected model returned HTTP 404.", "Check the API base path and exact model identifier. The error body was not retained."
    elif status in (400, 405, 415, 422):
        code, message, hint = "request_rejected", "The endpoint rejected this probe request.", "Inspect the plan. Check feature support, model settings, and --token-limit-field; no fallback was attempted."
    elif status is not None and status >= 500:
        code, message, hint = "upstream_error", "The endpoint returned a server error.", "Check provider health and gateway logs before retrying."
    else:
        code, message, hint = "http_error", "The endpoint returned an unsuccessful HTTP status.", "Check endpoint configuration. Remote error bodies are not saved."
    r.add(severity, code, message, hint)
    return r


def run_checks(config: Config) -> dict[str, Any]:
    specs = make_plan(config)
    if any(spec.method == "POST" for spec in specs) and not config.allow_inference:
        raise ValueError("Inference is disabled. Inspect the plan, then explicitly pass --allow-inference.")
    transport = Transport(config)
    results: list[ProbeResult] = []
    stop = False
    for spec in specs:
        if stop:
            results.append(skipped(spec.name, "Not run after an authentication, quota, network, or server failure."))
            continue
        try:
            result = inspect(spec.name, transport.request(spec), config)
        except TransportError as error:
            result = failure(spec.name, error)
            stop = error.code in ("timeout", "connection_error", "tls_error") or (
                error.http_status in (401, 403, 429) or (error.http_status is not None and error.http_status >= 500)
            )
        results.append(result)
    report = {
        "schema": SCHEMA,
        "mode": "live",
        "tool_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": {"origin": config.origin, "model": config.model, "id": config.target_id},
        "contract": contract(config),
        "plan": {"probes": list(config.probes), "max_requests": config.max_requests,
                 "timeout_seconds": config.timeout, "max_response_bytes": config.max_response_bytes},
        "summary": {status: sum(r.status == status for r in results) for status in ("pass", "warn", "fail", "skip")},
        "requests_attempted": sum(r.requests for r in results),
        "inference_requests_attempted": sum(r.requests for r in results if r.name != "models"),
        "results": [r.to_dict() for r in results],
    }
    # One final boundary also protects unusual keys embedded in user-supplied model/host strings.
    from .reporting import scrub
    report["target"]["origin"] = scrub(report["target"]["origin"], config.api_key)
    report["target"]["model"] = scrub(report["target"]["model"], config.api_key)
    return report
