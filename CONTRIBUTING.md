# Contributing

## Start with a reproducible observation

For a bug, describe the command with credentials removed, the expected behavior, and a minimal synthetic response or sanitized report. Never paste keys, confidential prompts, internal endpoint paths or unreviewed provider bodies. A provider/model name alone is not enough to reproduce a protocol issue; deployment and gateway settings can change behavior.

For a feature, explain which application requirement it helps validate and why it belongs in a small diagnostic rather than a router, general SDK or evaluation framework.

## Local checks

Python 3.10 or later is required. No installation is needed for the default suite:

```sh
python scripts/run_tests.py
python scripts/build_zipapp.py
python -I dist/llm-handshake.pyz demo --strict
```

The TLS tests use OpenSSL to create ephemeral certificates when that executable is available; otherwise those tests report explicit skips. Optional coverage uses `python -m pip install -e '.[dev]'`, then `python -m coverage run scripts/run_tests.py` and `python -m coverage report`.

Tests must not contact external providers or require credentials. Add fixtures that exercise the real local transport when fixing framing, timeout, TLS or byte-boundary behavior; a mocked method alone is not enough for those boundaries.

## Code and review expectations

Keep runtime dependencies at zero unless there is a compelling, documented tradeoff. Use type annotations at public boundaries, bounded parsing, deterministic synthetic fixtures and actionable static diagnostic text. Do not echo arbitrary provider strings or exception bodies into reports. Preserve the rule that a selected probe attempts at most one request.

Changing a request, probe meaning, or PASS criterion can invalidate baselines. Review whether `SUITE_VERSION` must change. Changing the report structure can require a new report schema. Keep existing failure codes stable when possible and explain changes in the changelog.

Update both READMEs for user-facing behavior. Put detailed reasoning and source links in the relevant documentation rather than inflating the command help. New third-party material needs exact origin/version, compatible licensing and retained notices. A similar feature in another project is not permission to copy its implementation.

Before merging, inspect the full diff, run the suite, test the standalone artifact, and verify that examples are clearly marked synthetic. CI configuration is not evidence that a workflow has passed; inspect actual runs after publication.

## Scope discipline

The project is not a model-ranking benchmark or a full compliance certification. Keep claims limited to tested observations. Avoid unverified provider compatibility badges, pricing tables that need constant updates, and defaults that trigger hidden inference. Prefer an explicit probe or user choice over automatic fallbacks that hide incompatibility.
