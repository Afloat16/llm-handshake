# Validation record

Recorded on **2026-09-30**, for version **0.1.0**.

## Executed locally

Environment: CPython **3.13.5**, Linux x86_64. Tests exercise local fixtures, including real HTTP and HTTPS sockets. They do not contact external model providers.

| Check | Observed result |
| :--- | :--- |
| `python scripts/run_tests.py` | **200 tests passed; 0 failures, 0 errors, 0 skips** |
| Branch-enabled runtime-package coverage | **97.33% combined**, 1,078/1,103 statements and 453/470 branches covered |
| Healthy loopback demonstration | 7 PASS; 7 attempted requests, of which 6 are local simulated inference requests |
| Broken loopback demonstration | 4 PASS, 1 WARN, 2 FAIL; missing usage and incorrect string-valued integer samples detected |
| Synthetic baseline comparison | 3 regressions; expected comparison exit code 3 |
| Actual local TLS handshakes | Added CA accepted, untrusted certificate rejected, mismatched hostname rejected |
| Deterministic zip-application build | Two builds from unchanged source produced identical bytes and SHA-256 |
| Isolated standalone application | `python -I .../llm-handshake.pyz demo --strict` passed without installed project dependencies |
| Clean wheel installation | Installed offline with `--no-index --no-deps` into a new virtual environment; console demo passed |
| Installed package inventory | Only the project and pip in the clean test environment |

Coverage measures the **runtime package**, not the entire repository or external subprocesses. The zero-covered `__main__.py` line in the in-process coverage report is exercised separately by the standalone/module entry-point smoke tests; those subprocess executions are not combined into the coverage percentage. Coverage is a testing aid, not evidence of absence of defects.

## Test areas

Configuration rejects unsafe/ambiguous URLs, unknown or repeated probes, invalid numeric limits, malformed keys and missing inference consent before requests. Plan tests verify payload selection, exact request counts and no network activity.

SSE tests include CR/LF/CRLF, multiline data, comments, UTF-8 and BOM handling, arbitrary two-part splits, seeded random fragmentation, incomplete final frames and bounded oversized input. Completion tests exercise malformed shapes, duplicate JSON keys, nonfinite values, deep nesting, numeric type mismatches, stream identities, usage accounting, tool reassembly and structured-output samples.

Transport tests cover real loopback GET/POST/SSE, stalled and byte-drip responses, status classifications, truncation, response/event limits, no redirect following, no environment-proxy use and no error-body echo. Real local TLS tests generate a temporary certificate/key with OpenSSL, then delete them; no private key is shipped.

Report and CLI tests cover secret redaction in user-controlled metadata, terminal/Markdown escaping, atomic output, symlink replacement, strict/required gates, mismatched contracts, removed/skipped probes and documented exit codes. Build tests inspect the archive and run it in a separate isolated Python process. Publication-helper tests cover identity and destination checks, explicit public consent, file allowlisting, ignored ambient host/repository overrides and refusal of existing local history.

## Reproduce

```sh
python scripts/run_tests.py
python scripts/build_zipapp.py
python -I dist/llm-handshake.pyz demo --strict
```

Optional coverage, with the development extra installed:

```sh
python -m coverage run scripts/run_tests.py
python -m coverage report
```

TLS tests explicitly skip when the OpenSSL executable is unavailable. All three TLS tests ran in the environment recorded above. Other platforms may have different filesystem and trust-store behavior.

## Not established by this record

No real hosted-provider calls, real Ollama deployment, real vLLM deployment, model-quality evaluation, load test, paid inference, or exhaustive protocol conformance test was performed. The examples' model name is a fixture identifier.

GitHub Actions is configured for Python 3.10–3.14 across three operating systems, but those remote jobs have not been executed as part of this local record. Likewise, the publication helper's safeguards are tested locally; actual GitHub repository creation and push require the maintainer's authenticated local GitHub CLI. Neither a prepared workflow nor a prepared publication script demonstrates remote success.

[Machine-readable validation summary](validation.json) · [Synthetic reports](../examples/README.md)
