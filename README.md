# LLM Handshake

**Find interface mismatches before they become application bugs.**

[English](README.md) · [简体中文](README.zh-CN.md)  
Python 3.10+ · MIT · Zero runtime dependencies

LLM Handshake is a small command-line diagnostic for OpenAI-compatible LLM endpoints. Preview the exact requests, run only the checks you need, and compare reports after a model or gateway change.

A successful chat request does not tell you whether streaming usage, tool-call arguments, or structured output will work. Handshake checks those behaviors separately, without a dashboard, database, provider SDK, or user documents.

## Try it without a key

From a source checkout:

```sh
python scripts/build_zipapp.py
python dist/llm-handshake.pyz demo
```

The demo starts an ephemeral loopback server, exercises the real HTTP client, and closes the server when finished. It never contacts a model provider.

```text
7 pass / 0 warn / 0 fail / 0 skip
Requests: 7 (6 inference)
```

The six inference requests above are **local mock requests**, not model executions. A deliberately broken demo demonstrates actionable findings:

```sh
python dist/llm-handshake.pyz demo --broken
```

```text
4 pass / 1 warn / 2 fail / 0 skip
WARN  stream-usage   usage_missing
FAIL  tool-stream    tool_arguments
FAIL  json           json_schema_sample
```

This command intentionally exits with code `1`. See the complete [synthetic example reports](examples/README.md).

### Install as a command

Inside a virtual environment, install the source directory:

```sh
python -m pip install .
llm-handshake demo
```

Installation may download the build backend; running the tool requires only Python's standard library. The `.pyz` route above also builds without third-party packages. A locally supplied wheel can be installed with `python -m pip install --no-index --no-deps PATH_TO_WHEEL`.

These are source and local-artifact installation instructions, not a claim of publication on PyPI.

## Check your endpoint

Set the **exact API base**, including any prefix such as `/v1`, and a model that your endpoint exposes. The tool does not guess a model, append `/v1`, or change token-limit parameters behind your back.

```sh
export OPENAI_BASE_URL="https://your-gateway.example/v1"
export OPENAI_MODEL="your-deployed-model"
# Provide OPENAI_API_KEY through your shell environment or secret manager.
# Do not place an actual credential in command arguments or committed files.
```

**Preview first — no requests are sent:**

```sh
llm-handshake plan --probes all --format json
```

**Inspect the model-list route — no inference is requested:**

```sh
llm-handshake check
```

**Opt in to seven checks, including six potentially billable inference requests:**

```sh
llm-handshake check --probes all --allow-inference
```

For a local endpoint that needs no authentication:

```sh
llm-handshake check \
  --base-url http://127.0.0.1:11434/v1 \
  --model "$OPENAI_MODEL" \
  --no-auth --probes chat,stream --allow-inference
```

The local example uses the endpoint shape documented by Ollama [R5]; it is not a claim that every installed model supports every probe. Use your actual installed model ID. On PowerShell, set variables with `$env:OPENAI_MODEL = "your-deployed-model"` and put commands on one line, or use PowerShell line continuation.

## What is checked?

| Probe | Request | Observation |
| :--- | :--- | :--- |
| `models` | `GET /models` | Readable catalog, nonempty IDs, duplicate IDs, selected-model presence |
| `chat` | One text completion | Completion envelope, assistant text, finish reason, reported token counts |
| `stream` | One plain stream | SSE framing, stable identity, text deltas, finish reason, `[DONE]` |
| `stream-usage` | A separate stream with `include_usage` | Usage values and terminal usage-only chunk, without conflating this with plain streaming |
| `tools` | One forced function selection | Call ID, function name, finish reason, parsed integer argument |
| `tool-stream` | One streamed function selection | Reassembly of name/argument fragments and validation of the completed call |
| `json` | One strict-schema request | Whether the returned sample matches the requested one-field integer object |

Each selected probe attempts at most one request. Returned tool calls are **never executed**. The `json` probe observes one sample; a model could satisfy the prompt while ignoring the schema parameter, so a pass does not prove schema enforcement. Protocol references and the rule-to-source map are in [PROTOCOL.md](docs/PROTOCOL.md).

## Useful workflows

### Require only the features your application needs

```sh
llm-handshake check \
  --probes chat,stream,stream-usage \
  --require chat,stream \
  --allow-inference
```

A warning about optional usage does not block this command, but `chat` and `stream` must both pass. Every required probe must also be selected; invalid combinations are rejected before network activity. Use `--strict` when **every selected probe** must pass.

### Save a report

```sh
llm-handshake check --probes all --allow-inference \
  --format json --output before.json

llm-handshake check --probes all --allow-inference \
  --format markdown --output diagnostic.md
```

JSON is the comparison format. Text and Markdown are for people. `--output` writes atomically, with owner-only permissions on POSIX; the parent directory must already exist. Existing output files are replaced. Shell redirection follows your shell's permissions instead.

### Catch a regression after an upgrade

Run the same check configuration again, save `after.json`, then:

```sh
llm-handshake compare before.json after.json
```

A lower probe status, a skipped formerly checked probe, or a missing probe is a regression. Changing the suite version or token settings makes reports incomparable. Changing the endpoint/model requires an explicit `--allow-target-change`. Timing and token-count fluctuations do not fail this gate. [Report semantics](docs/REPORTS.md)

### Use from Python

```python
import os
from llm_handshake import Config, run_checks
from llm_handshake.reporting import gate

report = run_checks(Config(
    base_url=os.environ["OPENAI_BASE_URL"],
    model=os.environ["OPENAI_MODEL"],
    api_key=os.environ.get("OPENAI_API_KEY", ""),
    probes=("chat", "stream"),
    allow_inference=True,
))
raise SystemExit(gate(report, required=("chat", "stream")))
```

## Predictable requests, explicit limits

The default `check` selects only `models`. Inference requires both selected inference probes and `--allow-inference`. The default all-probe plan has seven requests, six inference calls, and a requested output limit of 128 tokens per inference call: **768 requested output tokens in total**. This is **not a monetary budget**. Input and reasoning can be billed, providers may apply limits differently or ignore them, and failed requests may still consume resources.

`--max-requests` rejects a plan that is too large; it does not silently drop probes. The client has no automatic retries, parameter fallbacks, redirects, or proxy-environment support. Authentication failures, rate limiting, server errors, and connection/TLS/timeouts stop the remaining probes rather than repeatedly contacting a failing endpoint.

| Option | Default | Purpose |
| :--- | :--- | :--- |
| `--probes` | `models` | Comma-separated probe names, or `all` |
| `--timeout` | `20` seconds | Per-request socket/deadline limit; synchronous system DNS may exceed it |
| `--max-output-tokens` | `128` | Requested output limit; valid range 1–4096 |
| `--token-limit-field` | `max_tokens` | Explicitly choose `max_completion_tokens` for models requiring that field [R6] |
| `--max-requests` | `7` | Upper bound on the selected request plan |
| `--max-response-bytes` | `1048576` | Maximum consumed body bytes per successful response |
| `--api-key-env` | `OPENAI_API_KEY` | Environment variable containing the bearer token |
| `--no-auth` | Off | Ignore the key variable for a no-auth endpoint |
| `--ca-file` | System trust only | Add a PEM CA bundle without disabling certificate/hostname verification |
| `--allow-http` | Off | Explicitly permit non-loopback plaintext HTTP; avoid it with credentials |

`OPENAI_BASE_URL` and `OPENAI_MODEL` are optional environment defaults. Command flags take precedence. `.env` files are not loaded automatically. See `llm-handshake check --help` for all options.

## Privacy and safety

Only built-in synthetic prompts are sent, directly to the chosen endpoint. Reports do not retain API keys, response bodies, raw SSE events, provider error text, catalog model IDs, or full URL paths. There is no telemetry or remote report upload.

**JSON reports still identify the endpoint origin and selected model.** They also contain an unkeyed SHA-256 fingerprint of the normalized base URL and model; this is a correlation identifier, not anonymization. Review reports before sharing them. The tool cannot control provider logging, shell history, process inspection, or an untrusted local environment. [Security model](SECURITY.md)

## Exit codes

| Code | Meaning |
| :--- | :--- |
| `0` | Selected gate passed, or comparison found no status regressions |
| `1` | A probe failed, or a strict/required probe did not pass |
| `2` | Configuration, local I/O, or report-comparison input error |
| `3` | Comparison found at least one regression |
| `130` | Interrupted; no automatic retry |

A `WARN` is not a certification and missing usage is never treated as zero. A rejected request is not automatically labeled an unsupported capability. Output truncation, refusal, and filtering are reported as inconclusive observations.

## Scope and limitations

Version 0.1 targets a deliberately small **Chat Completions** surface, not every OpenAI-compatible feature. It does not test Responses, native Anthropic/Gemini APIs, embeddings, multimodal input, tool execution/follow-up turns, proxy behavior, HTTP/2, Azure-style query authentication, or all provider-specific parameters. It uses direct HTTP/1.1 and bearer authentication, or no authentication.

This is a diagnostic, not a model-quality benchmark, load test, billing meter, security audit, or complete conformance suite. One successful sample cannot guarantee future requests. `first_delta_ms` is client-observed time to the first nonempty text or tool-argument delta, including connection/network overhead; it is not provider inference latency. Perform an integration test in your real client as well.

Local HTTP/HTTPS tests and mock demonstrations are documented in [TESTING.md](docs/TESTING.md). No real-provider certification is implied.

## Why another tool?

LiteLLM addresses routing and provider abstraction [R1]; promptfoo addresses application evaluation and red teaming [R2]; LLM is a general command-line model interface [R3]. Existing Go compatibility testers also cover this category [R8, R9]. Handshake does not claim to invent endpoint testing. Its focus is a small Python executable, an inspectable request plan, separate stream-accounting diagnostics, and conservative report comparisons.

[Research and alternatives](docs/RESEARCH.md) · [References and attribution](docs/REFERENCES.md) · [Architecture](docs/ARCHITECTURE.md)

The implementation, synthetic fixtures, tests, and prose are independently written. Referenced projects are not runtime dependencies, their source is not vendored here, and their maintainers do not endorse this project.

## Development and maintenance

```sh
python scripts/run_tests.py
python scripts/build_zipapp.py
python -I dist/llm-handshake.pyz demo
```

Optional coverage: install the development extra, then run `python -m coverage run scripts/run_tests.py` and `python -m coverage report`. GitHub Actions is configured for Python 3.10–3.14 across Linux, macOS, and Windows; configured jobs are not the same as verified runs.

[Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Publishing guide](docs/PUBLISHING.md)

## License

[MIT](LICENSE). Copyright 2026 Afloat16. Third-party references are documented in [NOTICE](NOTICE) and [REFERENCES.md](docs/REFERENCES.md).

[R1]: https://github.com/BerriAI/litellm
[R2]: https://github.com/promptfoo/promptfoo
[R3]: https://github.com/simonw/llm
[R5]: https://docs.ollama.com/api/openai-compatibility
[R6]: https://platform.openai.com/docs/api-reference/chat/create
[R8]: https://github.com/beranekio/openai-compatibility-tester
[R9]: https://github.com/avelrl/openai-compatible-tester
