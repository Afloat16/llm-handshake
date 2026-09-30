# Reports and regression gates

## Format

Only JSON reports are accepted by `compare`. Text and Markdown are presentation formats. A JSON report contains:

| Field | Meaning |
| :--- | :--- |
| `schema` | Report format identifier, currently `llm-handshake.report.v1` |
| `mode` | `live` for an explicitly selected endpoint, `demo` for the local demonstration; “live” is a command mode, not a provider-certification claim |
| `tool_version`, `created_at` | Tool version and UTC timestamp |
| `target` | Displayed origin/model and SHA-256 fingerprint of normalized base URL plus model |
| `contract` | Suite version, requested output limit, and token-limit field |
| `plan` | Selected probes and request/time/response-size configuration |
| `summary` | Number of aggregate PASS/WARN/FAIL/SKIP results |
| `requests_attempted` | Number of transport attempts, not proof that a provider received or billed them |
| `inference_requests_attempted` | The inference subset of attempts |
| `results` | Named results with status, fixed findings, HTTP status, request count and bounded metrics |

A finding has `status`, `code`, `message`, `hint`, and `path`. The path describes an expected response location, not a path on the local filesystem. Findings are deduplicated by rule and path. Individual findings can include a passing note even when another finding makes the aggregate result FAIL.

Metrics may include response bytes, request duration, event count, first meaningful delta time, token counts, model count and whether the selected model was listed. Raw response text and catalog IDs are not retained. Not every metric exists for every result.

## Privacy

The full base path is excluded, but the origin and chosen model can still be sensitive. The fingerprint is **not a secret or anonymization mechanism**: it can correlate reports and guessed targets can be hashed for comparison. The API key is not part of the fingerprint. Sharing a report is the user's decision; there is no upload command.

`--output` creates a temporary file in the same directory, flushes it, then atomically replaces the requested destination. On POSIX the new file mode is 0600. A final-path symlink is replaced rather than followed. Parent directory trust and permissions remain the caller's responsibility. Windows access control depends on the directory's ACLs.

## Comparison policy

Reports must have the same suite version and token settings. They must identify the same normalized API base and model, unless `--allow-target-change` explicitly permits comparison of different targets. This override does not bypass a contract mismatch.

Status order is:

`PASS > WARN > FAIL > SKIP > missing`

Any downward transition for a previously present probe is a regression. A previously present probe that disappears is always a regression. A newly added probe is marked `added`, not an improvement to a nonexistent baseline result. An added FAIL does not itself create a baseline regression: also gate the current run to catch newly introduced failing checks.

A report with fewer selected checks therefore cannot quietly turn a failing comparison green. However, two equally failing reports have no status regression. **No regression is not the same as healthy.** Use both the `check` exit code and the `compare` exit code in CI.

Durations, token counts and numeric fluctuations are not compared. Timeout, response-size and request-cap settings are stored in the plan but are not part of the comparison contract; keep them consistent when interpreting results. The fingerprint does not encode the actual backend version, alias routing or tenant permissions. Capture deployment details separately when those matter.

The input validator protects the fields used by comparison: bounded input size, bounded JSON structure, schema identifier, target fingerprint, contract and unique known probe/status entries. It is not a full arbitrary-report JSON Schema validator. Unknown non-comparison fields are ignored. Reports are unsigned local artifacts, not tamper-proof attestations; compare trusts the statuses in the supplied files.

## Synthetic example

The reports in [examples](../examples/README.md) are explicitly marked `mode: demo`. Each demonstration uses a new local port, so its target fingerprint differs. The documented comparison uses `--allow-target-change` for that reason; it must not be interpreted as a real model upgrade test.

```sh
llm-handshake compare examples/healthy.demo.json examples/broken.demo.json \
  --allow-target-change
```

Expected exit code: `3`. Regressions: `stream-usage`, `tool-stream`, `json`.
