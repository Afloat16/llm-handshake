# References and attribution

Research cutoff and observation date: **2026-09-30**. These are primary project pages, primary issue reports, or official specifications/documentation. Repository popularity is only a discovery signal, not evidence of correctness. GitHub's rounded displayed star counts are preserved in [research-snapshot.json](research-snapshot.json).

## Project landscape

| ID | Source | Material reviewed and relevance |
| :--- | :--- | :--- |
| R1 | [BerriAI / LiteLLM](https://github.com/BerriAI/litellm) | Public README and repository overview. Provider routing and abstraction are outside this project's scope; interface checks can complement a gateway. |
| R2 | [promptfoo / promptfoo](https://github.com/promptfoo/promptfoo) | Public README and repository overview. Application evaluation and CI workflows are distinct from small wire-protocol checks. |
| R3 | [simonw / LLM](https://github.com/simonw/llm), [official documentation](https://llm.datasette.io/) | Public README/documentation overview. General-purpose command-line access is already well served; this project stays diagnostic. |
| R4 | [OpenAI / openai-python](https://github.com/openai/openai-python) | Official SDK README. SDKs are useful production clients, but a direct transport makes this diagnostic's request count and parameter choices explicit. No SDK code is used. |
| R8 | [beranekio / openai-compatibility-tester](https://github.com/beranekio/openai-compatibility-tester/blob/main/README.md) | README, including its SDK-based Go/Docker approach and suite selection. Closely related prior work; not a source-code dependency. README blob SHA at review: `8cfd5023a0ba9112ea2aeae4abced80b86534de6`. |
| R9 | [avelrl / openai-compatible-tester](https://github.com/avelrl/openai-compatible-tester/blob/master/README.md) | README, including compat/strict modes and client-oriented testing. Closely related prior work with broader surfaces. README blob SHA at review: `67d1c790aab990aa8f8468db7826c941c2815b7d`. |

The SHA values above identify the README blobs returned at review; they are not commit identifiers or repository-wide audits. Neither competitor's implementation was used as a template. This project does not claim to be the first endpoint-compatibility tester or to replace those projects' broader suites.

## Protocol and distribution documentation

| ID | Source | What it informs |
| :--- | :--- | :--- |
| R5 | [Ollama — OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) | A documented local endpoint shape and the reality that compatibility is scoped to supported features. Local examples are not provider-certification results. |
| R6 | [OpenAI — Chat Completions API reference](https://platform.openai.com/docs/api-reference/chat/create) | Public request/response field names and the small Chat Completions subset observed by `plan.py` and `validators.py`. The page currently redirects into the developers API reference. |
| R7 | [WHATWG HTML — Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html) | Independent implementation of UTF-8 framing, line endings, data-line accumulation and blank-line dispatch in `sse.py`. Browser reconnection behavior is intentionally outside scope. |
| R13 | [GitHub CLI — gh repo create](https://cli.github.com/manual/gh_repo_create) | The documented `--public`, `--source`, `--remote`, and `--push` flags used by the initial-publication helper. |
| R14 | [Python — zipapp](https://docs.python.org/3/library/zipapp.html) | Python's executable ZIP application format. The local builder writes a deterministic ZIP with an entry point; it does not vendor another builder. |
| R15 | [OpenAI — Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs) | The distinction between structured-output requests, sample validation, and exceptional outcomes such as refusal. Handshake does not certify schema enforcement. |

## Observed integration failures

Issue reports are evidence that a failure was **reported**, not proof of its prevalence or that a provider still has the same behavior. No confidential reproducer, provider credential, or upstream code snippet is included in this repository.

| ID | Report | Reported date | Design consequence |
| :--- | :--- | :--- | :--- |
| R10 | [tidyverse/ellmer #706 — missing streamed usage](https://github.com/tidyverse/ellmer/issues/706) | 2025-08-11 | Missing accounting metadata must remain distinguishable from valid zero token usage and from text streaming itself. |
| R11 | [anomalyco/opencode #31156 — stream_options rejected](https://github.com/anomalyco/opencode/issues/31156) | 2026-06-06 | Plain streaming and the `include_usage` extension are separate requests. Do not automatically inject the extension into every streaming check. |
| R12 | [microsoft/vscode #329436 — streamed usage not shown](https://github.com/microsoft/vscode/issues/329436) | 2026-08-06 | Direct endpoint checks and application integration tests answer different questions. A healthy endpoint cannot prove that a downstream client consumes its metadata correctly. |

At observation, R10 was closed, R11 was closed as not planned, and R12 was open with an information-needed label. These states are historical observations, not live status badges.

## CI dependencies

The workflow uses the following externally executed GitHub Actions, pinned to commits resolved from official release tags on 2026-09-30. They are not bundled into the Python package.

| Action | Reviewed release | Pinned commit |
| :--- | :--- | :--- |
| [actions/checkout](https://github.com/actions/checkout/releases/tag/v7.0.1) | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| [actions/setup-python](https://github.com/actions/setup-python/releases/tag/v7.0.0) | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |

Resolution sources: [checkout tag ref](https://api.github.com/repos/actions/checkout/git/ref/tags/v7.0.1) and [setup-python tag ref](https://api.github.com/repos/actions/setup-python/git/ref/tags/v7.0.0). Review Dependabot's proposed pin updates before merging them.

## Authorship and reuse boundary

Project source, tests, synthetic fixtures, and documentation are independently written. No third-party implementation is copied, translated, renamed, or vendored. Public protocol field names and documented wire behavior are used for interoperability; the user-facing product design and status-gating policy are project choices.

There are no runtime package dependencies. Setuptools is a build tool, and coverage is an optional development tool. Their distributions are not bundled here. The project license applies to this repository, not to linked external works. See [NOTICE](../NOTICE).

When a future contribution brings in code, test vectors, images, or prose from another work, record the exact origin and version, verify license compatibility, and preserve required notices. A URL alone is not a substitute for required license attribution.
