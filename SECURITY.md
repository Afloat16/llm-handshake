# Security policy

## Intended use

Run the CLI locally against an endpoint you are authorized to access. The base URL determines where the request and any bearer credential are sent. Review it carefully. Do not expose this library as an unauthenticated service that accepts arbitrary URLs; it has no multi-tenant SSRF allowlist or sandbox.

## Credential and data handling

The runtime reads a bearer token from a named environment variable, unless `--no-auth` is used. It does not accept a literal key argument, read user documents, load `.env` files, persist credentials, or upload reports. Ordinary reports use fixed findings and discard provider text. A key embedded into a displayed target value is replaced with a redaction marker, but this is not a universal secret scanner.

API origins, selected model names and unkeyed target fingerprints remain in JSON reports. Review them before sharing. Raw response bodies are processed in memory, not securely wiped. Local administrators, debuggers, shell configuration and untrusted code in the process can access sensitive material. Provider-side logging and retention are outside the tool's control.

Never put keys, private endpoints, confidential responses or customer data in public issues. The built-in fixtures use synthetic content only.

## Network protections and deliberate omissions

TLS verification is enabled. `--ca-file` adds trust without disabling hostname verification. Remote plaintext HTTP requires an explicit override; literal loopback addresses and localhost are allowed for local tools. Local hostname resolution is trusted. The client does not follow redirects, so it does not forward the credential to a redirected target. It ignores proxy environment variables and sends directly to the selected host.

Each selected probe attempts one request, and there are no automatic retries. Request counts, response bytes, JSON depth and SSE event size/count are bounded. A socket/deadline mechanism limits network waits, but synchronous OS DNS may exceed the requested timeout. Use external process isolation/time limits when operating under hostile resolver or operating-system conditions.

The client sends synthetic inference requests only after explicit consent. Small output limits are not a monetary cap. The provider might bill for input, reasoning, failed requests or limits interpreted differently. Use a restricted credential and provider-side spend controls appropriate to your environment.

## Local files

The CLI only writes to a path explicitly passed as `--output`. It replaces an existing file there atomically; it does not silently preserve the prior report. On POSIX, newly written reports have owner-only permissions. A destination symlink is replaced, not followed. Trusted parent directories and Windows directory ACLs remain the user's responsibility.

The `.pyz` contains only this project's runtime source and license, not a Python interpreter or vendored packages. Build it from reviewed source and verify artifact checksums obtained through a trusted channel. Checksums detect accidental changes; they are not signatures or proof of authorship.

## Development and publication

CI uses commit-pinned GitHub Actions, read-only repository permissions, synthetic loopback tests, and no model-provider secrets. Optional TLS fixture generation uses the local OpenSSL executable and deletes its temporary certificate and key when finished.

The initial-publishing script requires explicit `--public`, verifies the authenticated personal account, uses an allowlist of source paths, refuses an existing destination or enclosing Git history, and never force-pushes. The allowlist is not a content scanner: review all selected files before publication. The script uses the user's local GitHub CLI authentication and does not ask for a token in this application.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting channel when the repository has it enabled. Otherwise, first ask the maintainer for a private reporting channel without including exploit details or secrets in a public issue. Do not assume a private channel is enabled just because this file exists.

Include the affected version, a synthetic reproduction, expected boundary, observed result, and the smallest safe example. Avoid live credentials and third-party confidential data. No guaranteed response time is asserted.

## Supported versions

The current development line is 0.1.x. There is no promise of backported security fixes for older versions; check the changelog and maintained branch before deployment.
