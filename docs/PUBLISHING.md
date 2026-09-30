# Initial publication and releases

## Initial public repository

Review the source and the [security policy](../SECURITY.md) before publication. The helper only supports a **new personal repository**. It will not change an existing repository's visibility or overwrite its history.

Requirements: Python 3.10+, Git, and an installed [GitHub CLI](https://cli.github.com/manual/gh_repo_create). Authenticate locally:

```sh
gh auth login --hostname github.com
```

From a **freshly extracted source archive**, outside any other Git checkout:

```sh
python scripts/publish.py --owner Afloat16 --repo llm-handshake --public
```

This publishes the reviewed allowlisted source, not `.env` files, generated reports, build directories, private keys or caches. It runs tests, initializes a new `main` branch, uses a GitHub noreply commit address, creates the public repository, pushes once, and verifies public visibility and matching local/remote commit IDs.

The command intentionally refuses a mismatched logged-in account, existing destination, enclosing Git history, source symlink, missing required file, ambiguous availability response or failed tests. It never force-pushes and never asks you to paste a personal access token into this project. Its argument allowlist is not a secret-content scanner: a secret inside an otherwise allowed `.py` or `.md` file still requires your review.

The actual create/push behavior relies on the official `gh repo create --public --source ... --remote origin --push` interface. See reference R13 in [REFERENCES.md](REFERENCES.md). Test coverage of the helper includes local decision and safety behavior; only a successful remote verification establishes that publication completed.

A late network or permission failure can leave a local commit or a partially created remote. Do not delete a remote or force-push to “fix” a failed attempt. Inspect the state locally, review the staged/committed source, and complete the ordinary Git workflow. The helper is deliberately not an automatic recovery mechanism.

For an existing reviewed Git checkout, use the documented GitHub CLI/Git workflow directly rather than this new-repository helper. Check your remote and full history first.

## After publication

Inspect the actual GitHub Actions runs. The workflow contains no provider secrets or live inference tests. The configured matrix covers Python 3.10–3.14 on Linux, macOS and Windows, but coverage of an environment should only be claimed after that environment passes.

Enable private vulnerability reporting in repository settings when available. Select repository topics such as `llm`, `openai-compatible`, `diagnostics`, `streaming`, `python`, and `developer-tools`. These settings are optional and are not silently changed by the helper.

Add project URLs to `pyproject.toml` only after the repository exists. Keep the English README as the default and retain the link to the Chinese README. Avoid claiming package-registry publication until the registry confirms the upload.

## Release artifacts

The standalone application is built entirely with the standard library:

```sh
python scripts/build_zipapp.py
python -I dist/llm-handshake.pyz demo --strict
```

The build writes `dist/llm-handshake.pyz` and its SHA-256 sidecar. Its archive entry order, timestamps and stored bytes are deterministic for unchanged source. The archive contains the runtime Python files, `py.typed`, an entry point and the license. Python itself is not bundled.

To create ordinary Python distribution files with an installed compatible build backend:

```sh
python -m pip install 'setuptools>=77'
python -c "import setuptools.build_meta as b; b.build_wheel('dist'); b.build_sdist('dist')"
```

Review the artifact contents and install the wheel in a clean virtual environment before distributing it. The sdist is a build source package; the curated delivery source ZIP also provides a fresh directory suitable for the initial-publishing helper.

A GitHub release is separate from making a repository public. After reviewing the commit and pushing a release tag, use `gh release create` or the GitHub release interface to upload reviewed artifacts and their checksums. Do not use an unverified `latest` download link or a passing-CI badge as a substitute for release verification.

## Maintenance checklist

Update the version and changelog deliberately. Run tests and the isolated executable. Confirm that bilingual examples match current commands. Review references and notices for new material. Review the source allowlist and verify no secrets entered fixtures or examples. Record which environments and providers were actually tested. Keep stable finding codes and bump the suite contract when semantics require a new baseline.
