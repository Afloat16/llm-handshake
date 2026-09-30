# Probe contract and interpretation

Current report schema: `llm-handshake.report.v1`. Current suite contract: `1`.

Handshake checks a practical subset of wire behavior, not every field required by every specification. PASS means that the selected sample passed the implemented checks. It does not mean a full conformance certificate, successful downstream SDK parsing, or reliable support across all prompts.

## Source-to-rule map

References use the IDs in [REFERENCES.md](REFERENCES.md).

| Area | Basis | Implementation policy |
| :--- | :--- | :--- |
| Completion objects | R6, public Chat Completions fields | Require nonempty ID/model, valid timestamp/object marker, one index-zero assistant choice and a suitable finish reason |
| SSE framing | R7 | UTF-8, initial BOM handling, LF/CRLF/CR, comment lines, multiline data, blank-line dispatch; incomplete EOF frame discarded |
| Plain streaming | R6 | Inspect deltas, role, stable response identity, completion reason and terminal marker; do not request usage by default |
| Streamed accounting | R6, integration reports R10–R12 | Separate request with `include_usage`; missing usage warns, malformed counts fail; nonterminal or multiple accounting chunks warn |
| Tool selection | R6 | Request one named function and validate one integer argument; no tool execution or tool-result turn |
| Structured sample | R15 | Ask for a strict one-field schema, then validate the returned sample independently; no enforcement claim |
| Local endpoint examples | R5 | Preserve the exact supplied base prefix; do not generalize a documented endpoint into universal model support |
| Request limits and comparison ordering | Project policy | Explicit consent, one request per probe, fail-fast, status-based baseline comparison |

## Exact requests

`plan --format json` is the authoritative inspectable output for request payloads. The synthetic prompt asks for a short response; `chat` checks usable text, not exact spelling of the requested word. Both tool probes request `handshake_echo` with `{"value": 7}`. The JSON probe requests an object with that exact field and integer value.

Only the `stream-usage` probe requests `stream_options`. The other streams can pass even when that extension is rejected. The two results should not be merged into a single universal “streaming supported” label.

`--token-limit-field` explicitly selects either `max_tokens` or `max_completion_tokens`. There is no model-name heuristic, automatic retry with the other field, or unconditional temperature parameter. Reasoning-heavy models may exhaust a small limit before producing visible content; truncation is an inconclusive warning, with a suggestion to deliberately rerun using an appropriate limit.

## Usage values

Expected reported counters are nonnegative integers, excluding booleans. Total must equal input plus output. Counts above the JavaScript-safe integer range are rejected for report interoperability. Missing counters remain missing; they are not estimated from text or tokenizer libraries. The diagnostic does not price tokens, sum cumulative stream chunks, or reconstruct a bill.

For `stream-usage`, a single non-null accounting object in an empty-choices chunk after a finish reason is the expected shape. If an otherwise valid usage object is attached to a content chunk, the observation is a warning because client interpretation may differ. Valid terminal usage-only chunks must not be mistaken for invalid empty completions.

## Tool streams

The suite requests one tool, so the single tool index is zero. It accumulates function-name and argument fragments, preserves the call identity, and validates the completed argument JSON. Empty fragments do not count as a first argument delta. Non-string argument fragments, changing IDs, wrong names, stringified integers, and incorrect finish reasons are distinct diagnostics where possible.

This is not a parallel-tool test, argument-schema fuzz test, or execution test. No provider-supplied function name or argument is evaluated as code.

## Status policy

`PASS` is a successful observation. `WARN` means missing optional metadata or an inconclusive/limited observation. `FAIL` means a failed request or violated implemented check. `SKIP` means the probe did not run, usually because a preceding critical failure halted the plan.

A missing model-list route or unlisted chosen model does not prove inference is unavailable. A request rejected with HTTP 400 or 422 does not by itself prove permanent lack of support. Authentication, rate limiting and server errors retain their separate categories. Refusal, filtering and output-length exhaustion must not be silently converted to capability failures.

Default gates reject FAIL. `--strict` rejects anything other than PASS. `--require` names a selected subset that must PASS. Use the gate that matches the application's requirements, not an assumption that every optional feature is mandatory.

## Transport caveats

Only direct HTTP/1.1 and uncompressed responses are supported. TLS certificate and hostname verification remain enabled, including with an added CA. Proxies, redirects, WebSockets, HTTP/2, browser EventSource reconnection, custom authentication headers and arbitrary provider extra fields are outside version 0.1.

The reader stops at `[DONE]`; it is not a persistent stream monitor. Latency is a client-side observation from one request. The JSON field `first_delta_ms` includes connection and transport time, and is only present when meaningful text or tool arguments were actually observed.
