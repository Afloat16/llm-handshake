# LLM Handshake

**4 pass / 1 warn / 2 fail / 0 skip** · 7 requests

| Probe | Result | Observation |
| :--- | :--- | :--- |
| models | PASS | The selected sample passed its checks. |
| chat | PASS | The selected sample passed its checks. |
| stream | PASS | The selected sample passed its checks. |
| stream-usage | WARN | Token usage was not reported. |
| tools | PASS | The selected sample passed its checks. |
| tool-stream | FAIL | The returned JSON does not match the requested integer-object sample. |
| json | FAIL | The returned JSON does not match the requested integer-object sample. |

## Next steps

- Do not infer zero usage. Inspect the provider or gateway accounting settings.
- Inspect structured-output or tool-argument serialization for the selected model.

## Scope

One synthetic sample per probe, not a certification or billing estimate.
No credentials, response bodies, model-list entries, or full URL paths are included.
The JSON report contains the endpoint origin and selected model; review before sharing.
