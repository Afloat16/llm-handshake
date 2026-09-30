"""Bounded observations of the Chat Completions wire contract.

The checks observe one synthetic sample. They do not certify a provider, prove
schema enforcement, measure intelligence, or execute returned tool calls.
"""
from __future__ import annotations

import json
import math
from typing import Any

from .config import Config
from .models import ProbeResult
from .transport import WireResponse


def load_json(value: str | bytes) -> Any:
    def bad_constant(_: str) -> None:
        raise ValueError("Non-finite JSON numbers are not supported.")

    def integer(text: str) -> int:
        if len(text) > 20:
            raise ValueError("JSON integer exceeds the diagnostic size limit.")
        return int(text)

    def number(text: str) -> float:
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("Non-finite JSON numbers are not supported.")
        return value

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise ValueError("Duplicate JSON object keys are not supported.")
            out[key] = value
        return out

    if isinstance(value, bytes):
        value = value.decode("utf-8")
    # Bound nesting before entering the interpreter's recursive JSON decoder.
    depth = 0
    quoted = False
    escaped = False
    for char in value:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 64:
                raise ValueError("JSON nesting exceeds the diagnostic depth limit.")
        elif char in "]}":
            depth -= 1
    return json.loads(value, parse_constant=bad_constant, parse_int=integer,
                      parse_float=number, object_pairs_hook=pairs)


def note(r: ProbeResult, status: str, code: str, message: str,
         hint: str = "", path: str = "") -> None:
    # One finding per rule, not per chunk: adversarial streams cannot flood reports.
    if not any(f.code == code and f.path == path for f in r.findings):
        r.add(status, code, message, hint, path)


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def envelope(data: dict[str, Any], r: ProbeResult, streaming: bool = False) -> None:
    for key in ("id", "model"):
        if not text(data.get(key)):
            note(r, "fail", "envelope_" + key, f"The response needs a nonempty {key} string.",
                 "Check gateway response serialization.", "/" + key)
    if type(data.get("created")) is not int or data["created"] < 0:
        note(r, "fail", "envelope_created", "The response needs an integer creation timestamp.",
             "Check gateway response serialization.", "/created")
    expected = "chat.completion.chunk" if streaming else "chat.completion"
    if data.get("object") != expected:
        note(r, "fail", "envelope_object", "The response has an unexpected object type.",
             "Confirm that this route uses Chat Completions, not Responses events.", "/object")


def usage(data: Any, r: ProbeResult, required: bool = True) -> None:
    if data is None:
        if required:
            note(r, "warn", "usage_missing", "Token usage was not reported.",
                 "Do not infer zero usage. Inspect the provider or gateway accounting settings.", "/usage")
        return
    keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    if not isinstance(data, dict) or any(
        type(data.get(k)) is not int or not 0 <= data[k] <= 9_007_199_254_740_991 for k in keys
    ):
        note(r, "fail", "usage_shape", "Usage must contain three nonnegative integer token counts.",
             "Check whether the gateway is dropping or stringifying token counts.", "/usage")
        return
    for key in keys:
        r.metrics[key] = data[key]
    if data["total_tokens"] != data["prompt_tokens"] + data["completion_tokens"]:
        note(r, "fail", "usage_sum", "Reported total tokens do not equal input plus output tokens.",
             "Inspect the upstream usage mapping before using it for accounting.", "/usage/total_tokens")


def value_object(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"value"} and type(value["value"]) is int and value["value"] == 7


def parse_value(raw: Any, r: ProbeResult, code: str, path: str) -> None:
    try:
        value = load_json(raw) if isinstance(raw, str) else None
    except (ValueError, UnicodeError, RecursionError):
        value = None
    if not value_object(value):
        note(r, "fail", code, "The returned JSON does not match the requested integer-object sample.",
             "Inspect structured-output or tool-argument serialization for the selected model.", path)


def check_tools(calls: Any, r: ProbeResult) -> None:
    if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
        note(r, "fail", "tool_calls_shape", "Exactly one forced tool call was expected.",
             "Choose a tool-capable model and check tool_choice support.", "/choices/0/message/tool_calls")
        return
    call = calls[0]
    if not text(call.get("id")) or call.get("type") != "function":
        note(r, "fail", "tool_identity", "The tool call needs an id and function type.",
             "Preserve tool-call identifiers through the gateway.", "/tool_calls/0")
    function = call.get("function")
    if not isinstance(function, dict) or function.get("name") != "handshake_echo":
        note(r, "fail", "tool_name", "The forced tool name was not returned.",
             "Check forced function selection and the model chat template.", "/tool_calls/0/function/name")
        return
    parse_value(function.get("arguments"), r, "tool_arguments", "/tool_calls/0/function/arguments")


def stopped_early(reason: Any, r: ProbeResult) -> bool:
    if reason == "length":
        note(r, "warn", "output_truncated", "The sample stopped at its output limit; capability is inconclusive.",
             "Rerun deliberately with a larger --max-output-tokens value. Reasoning may consume the limit.",
             "/choices/0/finish_reason")
        return True
    if reason == "content_filter":
        note(r, "warn", "content_filtered", "The synthetic sample was filtered; capability is inconclusive.",
             "Inspect the configured content policy without disabling required protections.",
             "/choices/0/finish_reason")
        return True
    return False


def inspect_models(data: Any, r: ProbeResult, config: Config) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        note(r, "fail", "models_shape", "Expected a JSON object with a data array.",
             "Check the API base path and model-list route.", "/data")
        return
    items = data["data"]
    ids = [item.get("id") for item in items if isinstance(item, dict)]
    if len(ids) != len(items) or not all(text(item) for item in ids):
        note(r, "fail", "model_ids", "Each model-list entry needs a nonempty id string.", path="/data/*/id")
        return
    if len(ids) != len(set(ids)):
        note(r, "warn", "duplicate_models", "The model list contains duplicate identifiers.", path="/data/*/id")
    r.metrics["model_count"] = len(items)
    if not items:
        note(r, "warn", "models_empty", "The endpoint returned an empty model list.",
             "Check credentials and model deployment configuration.")
    if config.model:
        listed = config.model in ids
        r.metrics["selected_model_listed"] = listed
        if not listed:
            note(r, "warn", "model_not_listed", "The selected model was not listed; inference support is still unknown.",
                 "Some gateways expose incomplete catalogs. Run an explicit chat probe to verify.")
    note(r, "pass", "models_received", "The model-list response was readable. Model identifiers are not saved.")


def inspect_chat(data: Any, r: ProbeResult) -> None:
    if not isinstance(data, dict) or "error" in data:
        note(r, "fail", "response_error", "The successful HTTP response was not a completion object.",
             "Check for error objects wrapped in HTTP 200 responses.")
        return
    envelope(data, r)
    usage(data.get("usage"), r)
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        note(r, "fail", "choices_shape", "Expected exactly one completion choice.", path="/choices")
        return
    choice = choices[0]
    if type(choice.get("index")) is not int or choice["index"] != 0:
        note(r, "fail", "choice_index", "The single choice must have integer index zero.", path="/choices/0/index")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        note(r, "fail", "assistant_message", "Expected an assistant message object.", path="/choices/0/message")
        return
    if stopped_early(choice.get("finish_reason"), r):
        return
    if message.get("refusal"):
        note(r, "warn", "refusal", "The synthetic request was refused; capability is inconclusive.")
        return
    if r.name == "tools":
        check_tools(message.get("tool_calls"), r)
        if choice.get("finish_reason") != "tool_calls":
            note(r, "fail", "tool_finish_reason", "A tool call must finish with tool_calls.", path="/choices/0/finish_reason")
        note(r, "pass", "tool_sample", "The tool response was inspected. No function was executed.")
    else:
        if choice.get("finish_reason") != "stop":
            note(r, "fail", "finish_reason", "Expected a normal stop finish reason.", path="/choices/0/finish_reason")
        if not text(message.get("content")):
            note(r, "fail", "content_missing", "No nonempty text content was returned.",
                 "Check model support and reasoning/output limits.", "/choices/0/message/content")
        elif r.name == "json":
            parse_value(message["content"], r, "json_schema_sample", "/choices/0/message/content")
            note(r, "pass", "json_sample", "One structured-output sample was inspected; schema enforcement is not proven.")
        else:
            note(r, "pass", "chat_received", "An assistant text response was received.")


def inspect_stream(wire: WireResponse, r: ProbeResult) -> None:
    done = False
    finish: str | None = None
    identity: tuple[Any, Any] | None = None
    content = False
    role_seen = False
    reported_usage: Any = None
    usage_chunks = 0
    calls: dict[int, dict[str, Any]] = {}
    r.metrics["event_count"] = len(wire.events)
    for event, at_ms in wire.events:
        if done:
            note(r, "fail", "data_after_done", "An event followed the terminal DONE marker.")
            continue
        if event.event == "error":
            note(r, "fail", "stream_error_event", "The stream contained an error event; details were not retained.")
            continue
        if event.data == "[DONE]":
            done = True
            continue
        try:
            chunk = load_json(event.data)
        except (ValueError, UnicodeError, RecursionError):
            note(r, "fail", "stream_json", "An SSE data event was not valid JSON.",
                 "Check event boundaries, multiline framing, and UTF-8 serialization.")
            continue
        if not isinstance(chunk, dict) or "error" in chunk:
            note(r, "fail", "stream_error_payload", "The stream contained a non-chunk or an error payload.")
            continue
        envelope(chunk, r, streaming=True)
        current = (chunk.get("id"), chunk.get("model"))
        if identity is None:
            identity = current
        elif identity != current:
            note(r, "fail", "stream_identity_changed", "Response id or model changed between stream chunks.",
                 "Preserve a single completion identity across the entire stream.")
        if chunk.get("usage") is not None:
            reported_usage = chunk["usage"]
            usage_chunks += 1
            # Validate every non-null usage object, not only the last one.
            usage(reported_usage, r)
            if r.name == "stream-usage" and (chunk.get("choices") != [] or finish is None):
                note(r, "warn", "usage_not_terminal", "Usage was not in an empty-choices chunk after the finish reason.",
                     "Some clients only consume the final usage-only chunk; inspect gateway serialization.")
        choices = chunk.get("choices")
        if not isinstance(choices, list):
            note(r, "fail", "stream_choices", "A stream chunk is missing its choices array.", path="/choices")
            continue
        if not choices:
            if chunk.get("usage") is None:
                note(r, "warn", "empty_stream_chunk", "An empty-choices chunk contained no usage object.",
                     "Inspect whether the gateway inserts metadata-only chunks.")
            continue
        if len(choices) != 1 or not isinstance(choices[0], dict):
            note(r, "fail", "stream_choice_count", "Expected one choice in content chunks.", path="/choices")
            continue
        choice = choices[0]
        if type(choice.get("index")) is not int or choice["index"] != 0:
            note(r, "fail", "stream_choice_index", "The streamed choice index must be integer zero.")
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            note(r, "fail", "stream_delta", "Expected an object-valued delta.", path="/choices/0/delta")
            continue
        if finish is not None:
            note(r, "fail", "choice_after_finish", "A choice chunk followed a finish reason.",
                 "Only a terminal usage chunk should follow a finished choice.")
        reason = choice.get("finish_reason")
        if reason is not None:
            if reason not in ("stop", "length", "tool_calls", "content_filter", "function_call"):
                note(r, "fail", "stream_finish_reason", "The stream used an unknown finish reason.")
            else:
                finish = reason
        if "role" in delta:
            if delta["role"] != "assistant":
                note(r, "fail", "stream_role", "The streamed role was not assistant.")
            else:
                role_seen = True
        piece = delta.get("content")
        if piece is not None and not isinstance(piece, str):
            note(r, "fail", "stream_content_type", "Text deltas must be strings or null.")
        if text(piece):
            content = True
            r.metrics.setdefault("first_delta_ms", round(at_ms, 3))
        if delta.get("refusal"):
            note(r, "warn", "refusal", "The synthetic request was refused; capability is inconclusive.")
        fragments = delta.get("tool_calls")
        if fragments is None:
            continue
        if not isinstance(fragments, list):
            note(r, "fail", "tool_delta_shape", "Streamed tool_calls must be an array.")
            continue
        for fragment in fragments:
            if not isinstance(fragment, dict) or type(fragment.get("index")) is not int or fragment["index"] != 0:
                note(r, "fail", "tool_delta_index", "The single forced tool must stream with index zero.")
                continue
            call = calls.setdefault(0, {"function": {"name": "", "arguments": ""}})
            for key in ("id", "type"):
                if key in fragment:
                    if not text(fragment[key]) or (key in call and call[key] != fragment[key]):
                        note(r, "fail", "tool_delta_identity", "A streamed tool id or type was invalid or changed.")
                    else:
                        call[key] = fragment[key]
            function = fragment.get("function", {})
            if not isinstance(function, dict):
                note(r, "fail", "tool_delta_function", "A tool function delta must be an object.")
                continue
            for key in ("name", "arguments"):
                if key not in function:
                    continue
                if not isinstance(function[key], str):
                    note(r, "fail", "tool_delta_text", "Tool name and argument fragments must be strings.")
                else:
                    call["function"][key] += function[key]
                    if key == "arguments" and function[key]:
                        r.metrics.setdefault("first_delta_ms", round(at_ms, 3))
    if not done:
        note(r, "fail", "done_missing", "The stream ended without a framed [DONE] marker.",
             "Check truncation, proxy buffering, and the final blank SSE line.")
    if finish is None:
        note(r, "fail", "finish_missing", "The stream never reported a finish reason.")
    if not role_seen:
        note(r, "warn", "stream_role_missing", "No assistant role delta was observed.",
             "Some clients need the initial assistant role chunk.")
    early = stopped_early(finish, r)
    refused = any(f.code == "refusal" for f in r.findings)
    if not early and not refused:
        if r.name == "tool-stream":
            check_tools(list(calls.values()), r)
            if finish != "tool_calls":
                note(r, "fail", "tool_finish_reason", "A streamed tool call must finish with tool_calls.")
        else:
            if not content:
                note(r, "fail", "stream_content_missing", "No nonempty text delta was observed.")
            if finish not in (None, "stop"):
                note(r, "fail", "stream_finish_reason", "Expected a normal stop for the text stream.")
    usage(reported_usage, r, required=r.name == "stream-usage")
    if r.name == "stream-usage" and usage_chunks > 1:
        note(r, "warn", "multiple_usage_chunks", "Multiple non-null usage chunks were observed.",
             "Do not sum cumulative usage chunks as separate requests.")
    note(r, "pass", "stream_inspected", "Stream framing and payloads were inspected. Raw events are not saved.")


def inspect(name: str, wire: WireResponse, config: Config) -> ProbeResult:
    r = ProbeResult(name, http_status=wire.status)
    r.metrics.update(duration_ms=wire.elapsed_ms, response_bytes=wire.byte_count)
    if name in ("stream", "stream-usage", "tool-stream"):
        inspect_stream(wire, r)
        return r
    try:
        data = load_json(wire.body)
    except (ValueError, UnicodeError, RecursionError):
        note(r, "fail", "invalid_json", "The HTTP body was not a valid bounded UTF-8 JSON document.",
             "Check whether an HTML error page, duplicate keys, or non-finite numbers were returned.")
        return r
    if name == "models":
        inspect_models(data, r, config)
    else:
        inspect_chat(data, r)
    return r
