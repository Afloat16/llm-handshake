# Architecture

## Execution path

`CLI / Python Config → immutable configuration → request plan → bounded transport → validators → report → optional gate/comparison`

There is no plugin loading, shell execution, background daemon, telemetry, local database, retry queue, or credential store in the runtime package.

| Module | Responsibility |
| :--- | :--- |
| `config.py` | Validate options, normalize the API base, select probes in canonical order, fingerprint the target |
| `plan.py` | Build synthetic request descriptions and the comparison contract, without I/O |
| `transport.py` | Direct HTTP/HTTPS, time/byte/event limits, TLS verification, error-body suppression |
| `sse.py` | Incremental UTF-8 and SSE event framing, independent of completion semantics |
| `validators.py` | Bounded JSON decoding, response observations, safe fixed diagnostic messages |
| `models.py` | Finding/result objects, schema and suite identifiers |
| `runner.py` | Consent check, sequential execution, fail-fast policy, sanitized report construction |
| `reporting.py` | Text/JSON/Markdown rendering, atomic local writes, status gates and offline comparison |
| `mock.py` | Temporary loopback fixtures for demonstrations and tests, never a production server |
| `cli.py` | Argument parsing, environment defaults, command dispatch, documented exit codes |

## Why direct HTTP rather than a provider SDK?

The direct transport deliberately makes a single attempted request correspond to a single probe. Request extensions are not inserted by middleware, redirects are not followed, and retries cannot silently expand a diagnostic run. This is not a recommendation to replace SDKs in production applications. It trades protocol breadth for a small, inspectable behavior boundary.

SSE framing follows the relevant part of [WHATWG's specification](REFERENCES.md); the parser does not implement a browser EventSource reconnect loop. The `[DONE]` marker is a completion-stream convention interpreted outside the framing parser.

## Boundaries and limits

Configuration validation happens before transport construction; the runner refuses inference without consent. Invalid CA configuration also fails before a request. A plan exceeding the request cap is rejected as a whole. The currently registered seven probes run sequentially, with no worker pool.

The transport consumes at most the configured successful-response body byte limit (default 1 MiB, maximum 8 MiB), with an additional SSE event-count limit of 4,096 and per-frame character limit of the smaller of 262,144 and the response limit. A parser feed can transiently produce a bounded batch before the event-count check; the raw byte cap still applies. JSON decoding rejects duplicate keys, nonfinite numbers, integer literals longer than 20 characters, and nesting beyond 64 levels. These are diagnostic resource policies, not general JSON validity rules.

Socket operations use a timeout. A timer closes an available connection at the per-request deadline so a slow byte-drip cannot continually reset an inactivity timeout. Synchronous system DNS is outside Python's socket deadline control and may take longer. Do not describe this as a universal hard wall-clock guarantee.

HTTP errors are classified from the status code without reading response bodies. Successful SSE reads stop at a framed `[DONE]`. Extra events already present in the same parsed batch are visible to validation, but the tool does not wait for or inspect arbitrary later data after completion.

## Failure model

Authentication errors, rate limiting, server failures, TLS errors, timeouts, and connection failures skip remaining probes. A missing catalog route is only a warning because some usable endpoints omit it. A feature request rejected with a client error remains a rejection observation; the tool cannot reliably distinguish unsupported features from every possible model/configuration error.

A probe may contain both passing observations and failures. Its aggregate status uses the most severe finding, not the last message. Tests check that a reassuring final note cannot mask a prior failure.

## Data handling

The full base URL and bearer token exist in memory to construct the user's request. They are excluded from `Config`'s representation, and the token is never included in normal reports. Provider bodies are inspected in memory and discarded after validation; this is not guaranteed secure memory erasure.

Reports use fixed rule messages. Provider strings are not interpolated into findings. Only expected bounded numeric/boolean metrics are copied. User-controlled displayed target values are scrubbed for control characters and literal occurrences of the configured credential. The report fingerprint is unkeyed and must not be marketed as anonymization.

## Extension procedure

A new probe needs a planned payload, validator, deterministic positive and negative fixtures, request-count documentation, privacy review, and parity updates to both READMEs. Add it to the canonical ordering and comparison boundary. Change the suite version whenever request semantics or pass criteria change in a way that makes old and new reports incomparable.

New provider-specific exceptions should not silently weaken an existing PASS meaning. Prefer a clearly named separate probe or a documented intentional policy change. Keep raw-provider text out of errors even when an upstream response is malformed.

The initial-publishing helper is a separate development script with explicit public-publication consent. It is not imported into the runtime application.
