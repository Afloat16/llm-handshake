# Changelog

## 0.1.0 — 2026-09-30

Initial implementation, prepared for publication.

### Added

- Seven independently selectable endpoint probes: models, chat, stream, stream-usage, tools, tool-stream and JSON sample validation.
- Offline request planning, explicit inference consent, sequential bounded requests and critical-failure short-circuiting.
- Independent incremental SSE parsing, bounded JSON decoding and streamed tool-argument assembly.
- Text, JSON and Markdown reports with fixed diagnostics and no retained provider text.
- Strict/required gates and offline baseline comparison that detects removed and skipped probes.
- Key-free healthy/broken loopback demonstrations, real local TLS tests, and portable Python zip-application build tooling.
- English and Simplified Chinese READMEs, references, design records, security policy, CI configuration and guarded initial-publication helper.

### Scope

Chat Completions subset only. No real-provider certification, pricing estimate, complete schema-enforcement test, model-quality benchmark or tool execution is claimed.
