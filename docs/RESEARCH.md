# Why LLM Handshake?

Decision record · 2026-09-30

## The question

Which small LLM tool can help developers across model vendors without becoming another application framework, chat interface, or hosted platform?

The selected problem is **uncertainty at the model-endpoint boundary**: a base URL and a working text completion do not establish that the application's required request parameters and response shapes behave as expected. This is relevant when connecting a local server, a shared gateway, a new hosted endpoint, or a changed model deployment. It is not a claim that every LLM user needs this tool.

## Method

Review public READMEs of four established repositories, read official wire-format documentation, search for concrete compatibility failures, and inspect the two closest compatibility-testing alternatives. Compare scope and operational cost rather than equating stars with quality. The exercise is a focused landscape review, not an exhaustive census or a user survey.

The implementation follows documented protocols and independent synthetic fixtures. No implementation source from another diagnostic tool was used. Complete links and reviewed-material boundaries are in [REFERENCES.md](REFERENCES.md).

## Established projects and the boundary not to duplicate

GitHub-displayed counts below are rounded snapshots observed on 2026-09-30, not exact API counts.

| Project | Displayed stars | Existing job | Boundary chosen for Handshake |
| :--- | ---: | :--- | :--- |
| [LiteLLM](https://github.com/BerriAI/litellm) | 59.9k | Provider abstraction and gateway operations | Diagnose a chosen endpoint; do not route production traffic |
| [openai-python](https://github.com/openai/openai-python) | 31.7k | Official API client | Observe direct wire behavior; do not become another SDK |
| [promptfoo](https://github.com/promptfoo/promptfoo) | 25.6k | Prompt/application evaluation and red teaming | Check plumbing before application evaluation; do not grade model intelligence |
| [LLM](https://github.com/simonw/llm) | 12.6k | General-purpose CLI access to models | Provide a bounded diagnostic rather than a conversational command suite |

The projects above are useful alternatives for their intended jobs. The comparison does not assert that they cannot perform individual checks included here.

## Evidence beyond popularity

Three primary reports shaped the design:

**Missing streamed accounting can break an otherwise working client.** The ellmer report [R10](REFERENCES.md) describes working streamed text followed by failure in token logging. Handshake gives plain streaming and accounting independent results and never invents zero usage when metadata is absent.

**Request extensions can be the failure, not streaming itself.** An OpenCode report [R11](REFERENCES.md) describes a gateway rejecting `stream_options` while a request without that field works. Handshake sends a plain stream and an opt-in usage stream as different probes. It does not silently remove parameters and retry, because that would obscure the diagnosis and add requests.

**Endpoint correctness and application correctness are different.** A VS Code report [R12](REFERENCES.md) describes missing client-visible usage even when direct API testing found a final usage chunk. Handshake can narrow investigation to one boundary, but its report cannot certify a downstream client. The README explicitly recommends a real-client smoke test.

These reports are specific observations, not statistically representative failure rates. Their historical status and dates are recorded with the references.

## Closest alternatives

The category already exists. [beranekio/openai-compatibility-tester](https://github.com/beranekio/openai-compatibility-tester) documents a Go/SDK-based Docker harness with multiple API suites. [avelrl/openai-compatible-tester](https://github.com/avelrl/openai-compatible-tester) documents a Go harness with compat/strict interpretations, broader API surfaces, and client-oriented checks. Their READMEs were reviewed, not their implementation code.

These are appropriate candidates when broader endpoint coverage, SDK-specific behavior, or richer client profiles are needed. Handshake intentionally offers less surface area. Its product emphasis is the combination of a standard-library-only Python executable, a full preflight request plan, independently diagnosable streamed accounting, and versioned, conservative status comparisons.

None of these individual ideas is presented as novel. Differentiation is a usability and scope decision, not a claim of invention or measured superiority.

## Alternatives considered and rejected for the first version

| Candidate | Appeal | Why it was not selected |
| :--- | :--- | :--- |
| Multi-provider chat CLI | Broad audience, familiar workflow | Overlaps directly with mature clients; requires ongoing provider/UI breadth |
| Universal model router | Can centralize endpoint differences | Operationally heavy and too close to gateway projects |
| Prompt-quality evaluator | Useful for product changes | Needs representative tasks, metrics, and application context; not a tiny universal first step |
| Endpoint preflight and regression checks | Helps isolate common integration boundaries | Small enough to make requests, failure modes, and privacy behavior inspectable |

This table is a design assessment, not measured market research.

## Design decisions and costs

**No runtime dependencies.** A `.pyz` can run wherever a supported Python interpreter is available. The cost is maintaining a small HTTP/SSE implementation and explicitly omitting proxies, HTTP/2, and native provider-specific APIs. Extensive transport and framing tests are therefore essential.

**No hidden inference.** The default command checks the catalog route. Inference needs explicit consent, and `plan --format json` reveals every payload. The cost is one extra flag, which is preferable to surprising calls or charges.

**One sample per probe, no retry.** This makes the maximum request plan easy to understand. The cost is sensitivity to transient and nondeterministic behavior. A user can rerun deliberately; a single pass is not a reliability estimate.

**Status regressions, not benchmark scores.** A baseline report can fail CI when a required capability degrades or disappears. Latency, pricing and intelligence rankings are excluded because a few synthetic calls cannot support those claims. Users must choose their required subset; optional features are not globally necessary.

**No raw-response report.** Diagnostics are fixed messages and bounded metrics. This reduces accidental disclosure through shared reports but can require a separate, carefully controlled provider investigation for detailed root cause. The endpoint origin, selected model, and correlation fingerprint still need review.

## Who should try it first?

A developer changing a model endpoint; a team operating a gateway and checking client-facing behavior after deployment; a maintainer receiving an integration issue who needs a small synthetic reproduction. The first useful action is not “test everything”; it is to check exactly the capabilities the application requires.

For a nontechnical end user who only uses a hosted chat page, this CLI is not an essential tool. Broad applicability here means common infrastructure boundaries across LLM applications, not universal relevance.

## Maintenance priorities

Use real, sanitized integration reports to refine diagnostics without adding hidden fallbacks. A future Responses surface should be a separately versioned probe family, not mixed into Chat Completions results. Tool follow-up turns and provider-specific options should stay opt-in with visible request-count implications. Cross-platform CI and a small dependency surface should remain easier to maintain than a larger feature list.

Before claiming live-provider support, record the exact model, deployment settings, date, command, sanitized report, and known limitations. Local mock results are never substituted for provider validation.
