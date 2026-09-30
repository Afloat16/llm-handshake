# Synthetic examples

All reports in this directory come from the temporary loopback mock server. They are not results for an external provider or a real model. `mode` is `demo`; origin ports and timing observations vary by run and are not benchmark data.

| File | Purpose |
| :--- | :--- |
| [healthy.demo.json](healthy.demo.json) | Seven passing diagnostic results |
| [broken.demo.json](broken.demo.json) | Missing streamed usage, a string-valued streamed tool argument, and a string-valued JSON field |
| [broken.demo.md](broken.demo.md) | Human-readable corrective hints for the same broken fixture |
| [comparison.demo.json](comparison.demo.json) | Three observed status regressions across the two synthetic targets |
| [library_check.py](library_check.py) | Minimal real-endpoint library integration with explicit inference consent |

## Reproduce

After installing the package or replacing `llm-handshake` with `python dist/llm-handshake.pyz`:

```sh
llm-handshake demo --format json --output healthy.json
llm-handshake demo --broken --format json --output broken.json
llm-handshake compare healthy.json broken.json --allow-target-change
```

Expected exit codes in order: `0`, `1`, `3`. Run the commands separately; a shell configured to stop on the intentional failure will not execute the comparison automatically.

Each demo uses a different ephemeral local port, so the target-change flag is necessary here. For a real upgrade comparison, keep the same endpoint/model and settings; no target override should normally be needed.

The library example requires configured environment variables and **does call the selected endpoint**. It is not invoked by the default test suite or CI.
