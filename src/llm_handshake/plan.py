"""Independently authored synthetic protocol probes; no user files or prompts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Config
from .models import SUITE_VERSION

VALUE_SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "integer", "enum": [7]}},
    "required": ["value"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class RequestSpec:
    name: str
    method: str
    path: str
    payload: dict[str, Any] | None
    streaming: bool = False


def make_plan(config: Config) -> list[RequestSpec]:
    plan: list[RequestSpec] = []
    for name in config.probes:
        if name == "models":
            plan.append(RequestSpec(name, "GET", "/models", None))
            continue
        body: dict[str, Any] = {
            "model": config.model,
            "messages": [{"role": "user", "content": "Reply with the single word READY."}],
            config.token_limit_field: config.max_output_tokens,
        }
        streaming = name in ("stream", "stream-usage", "tool-stream")
        if streaming:
            body["stream"] = True
        if name == "stream-usage":
            body["stream_options"] = {"include_usage": True}
        if name in ("tools", "tool-stream"):
            body["messages"][0]["content"] = "Call handshake_echo with the integer value 7."
            body["tools"] = [{
                "type": "function",
                "function": {
                    "name": "handshake_echo",
                    "description": "Accept one integer and return it unchanged.",
                    "parameters": VALUE_SCHEMA,
                },
            }]
            body["tool_choice"] = {"type": "function", "function": {"name": "handshake_echo"}}
        if name == "json":
            body["messages"][0]["content"] = 'Return a JSON object with exactly one field: "value", set to integer 7.'
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "handshake_value", "strict": True, "schema": VALUE_SCHEMA},
            }
        plan.append(RequestSpec(name, "POST", "/chat/completions", body, streaming))
    return plan


def contract(config: Config) -> dict[str, Any]:
    return {
        "suite_version": SUITE_VERSION,
        "token_limit_field": config.token_limit_field,
        "max_output_tokens": config.max_output_tokens,
    }


def describe_plan(config: Config) -> dict[str, Any]:
    specs = make_plan(config)
    inference = sum(s.method == "POST" for s in specs)
    return {
        "schema": "llm-handshake.plan.v1",
        "target": {"origin": config.origin, "model": config.model, "id": config.target_id},
        "contract": contract(config),
        "request_count": len(specs),
        "inference_requests": inference,
        "requested_output_token_ceiling": inference * config.max_output_tokens,
        "billing_note": "Requested output limits are not a monetary cap. Input and reasoning may be billed; servers may ignore limits.",
        "requests": [
            {"probe": s.name, "method": s.method, "relative_path": s.path, "payload": s.payload}
            for s in specs
        ],
    }
