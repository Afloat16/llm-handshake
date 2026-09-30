#!/usr/bin/env python3
"""Publish a reviewed source checkout to a NEW personal public GitHub repo.

Requires local git and an authenticated GitHub CLI (gh). Does not accept tokens,
change visibility, overwrite an existing remote repository, or force-push.
For subsequent maintenance use the ordinary git review/commit/push workflow.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = {
    "README.md", "README.zh-CN.md", "LICENSE", "NOTICE", "CHANGELOG.md",
    "CONTRIBUTING.md", "SECURITY.md", "pyproject.toml", "MANIFEST.in",
    ".gitignore", ".gitattributes", ".editorconfig", ".env.example",
}
EXTENSIONS = {
    "src": {".py", ".typed"}, "tests": {".py"}, "scripts": {".py"},
    "docs": {".md", ".json"}, "examples": {".py", ".md", ".json"},
    ".github": {".md", ".yml", ".yaml"},
}


class PublishError(Exception):
    pass


def run(args: list[str], *, cwd: Path = ROOT, check: bool = True,
        capture: bool = True, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if args[0] == "gh":
        environment["GH_HOST"] = "github.com"
        environment.pop("GH_REPO", None)
    if args[0] == "git":
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
            environment.pop(name, None)
    result = subprocess.run(args, cwd=cwd, check=False, capture_output=capture,
                            text=True, timeout=timeout, env=environment)
    if check and result.returncode:
        # Do not dump arbitrary tool output; authenticated URLs could be present.
        raise PublishError(f"{args[0]} failed (exit {result.returncode}). Inspect that tool locally; no retry was made.")
    return result


def selected_files(root: Path) -> list[str]:
    """Allowlist source paths; never stage .env, caches, reports, keys or symlinks."""
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part.startswith(".git") for part in relative.parts if part not in (".github", ".gitignore", ".gitattributes")):
            continue
        if path.is_symlink():
            # Ignore paths outside the allowlisted source tree, but never follow them.
            if relative.parts[0] in EXTENSIONS or relative.as_posix() in TOP_FILES:
                raise PublishError("A source symlink was found. Replace it with a reviewed ordinary file.")
            continue
        if not path.is_file():
            continue
        top = relative.parts[0]
        if relative.as_posix() in TOP_FILES or (
            top in EXTENSIONS and path.suffix in EXTENSIONS[top]
            and "__pycache__" not in relative.parts
        ):
            files.append(relative.as_posix())
    if not {"README.md", "README.zh-CN.md", "LICENSE", "pyproject.toml"}.issubset(files):
        raise PublishError("Required release files are missing.")
    return files


def validate_identity(owner: str, repo: str, profile: dict) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", owner):
        raise PublishError("Invalid personal GitHub account name.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", repo) or repo.endswith(".git"):
        raise PublishError("Invalid repository name.")
    if str(profile.get("login", "")).casefold() != owner.casefold() or type(profile.get("id")) is not int:
        raise PublishError("The authenticated GitHub account does not match --owner. No repository was created.")


def require_new_repo(owner: str, repo: str) -> None:
    # Distinguish a confirmed 404 from permissions/network/server failures.
    result = run(["gh", "api", f"repos/{owner}/{repo}", "--hostname", "github.com", "--include"], check=False)
    status = re.search(r"^HTTP/\S+\s+(\d{3})\b", result.stdout or "", re.MULTILINE)
    if not status:
        raise PublishError("Could not confirm repository availability. No repository was created.")
    if status.group(1) == "200":
        raise PublishError("The destination repository already exists. This initial-publish script will not modify it.")
    if status.group(1) != "404":
        raise PublishError("GitHub did not confirm an absent repository. No repository was created.")


def publish(owner: str, repo: str, root: Path = ROOT) -> str:
    for executable in ("git", "gh"):
        if not shutil.which(executable):
            raise PublishError(f"Install {executable} first. For GitHub authentication, run: gh auth login --hostname github.com")
    profile = json.loads(run(["gh", "api", "user", "--hostname", "github.com"]).stdout)
    validate_identity(owner, repo, profile)
    files = selected_files(root)
    require_new_repo(owner, repo)

    # A fresh local repository only: this avoids accidentally publishing unrelated history.
    probe = run(["git", "rev-parse", "--show-toplevel"], cwd=root, check=False)
    if probe.returncode == 0:
        raise PublishError("A Git repository already contains this directory. Publish from a fresh extracted source archive, or use your reviewed git workflow.")
    print(f"Target: {owner}/{repo} (PUBLIC). Source files: {len(files)}. Running tests.", flush=True)
    run([sys.executable, "scripts/run_tests.py"], cwd=root, capture=False)
    run(["git", "init", "-b", "main"], cwd=root)
    run(["git", "config", "user.name", str(profile["login"])], cwd=root)
    run(["git", "config", "user.email", f"{profile['id']}+{profile['login']}@users.noreply.github.com"], cwd=root)
    # Disable hooks for staging and committing in this fresh checkout.
    run(["git", "-c", "core.hooksPath=/dev/null", "add", "--", *files], cwd=root)
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=root).stdout.splitlines()
    if set(staged) != set(files):
        raise PublishError("The staged file list differs from the allowlist. Review it locally; nothing was published.")
    run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "commit", "-m",
         "Initial release: bounded LLM endpoint compatibility checks"], cwd=root)
    run(["gh", "repo", "create", f"{owner}/{repo}", "--public", "--source", str(root),
         "--remote", "origin", "--push", "--description",
         "Zero-dependency LLM endpoint diagnostics: inspect requests, validate streaming, and catch compatibility regressions."],
        cwd=root, capture=False)
    local_sha = run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    remote = json.loads(run(["gh", "api", f"repos/{owner}/{repo}", "--hostname", "github.com"]).stdout)
    remote_sha = json.loads(run(["gh", "api", f"repos/{owner}/{repo}/commits/main", "--hostname", "github.com"]).stdout)["sha"]
    if remote.get("private") is not False or local_sha != remote_sha:
        raise PublishError("Creation or push may have partially completed, but public visibility and commit verification failed. Inspect GitHub before retrying.")
    url = f"https://github.com/{owner}/{repo}"
    print(f"Verified public repository: {url}\nCommit: {local_sha}")
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", default="llm-handshake")
    parser.add_argument("--public", action="store_true", help="Explicitly consent to publishing all selected source files publicly.")
    args = parser.parse_args()
    if not args.public:
        parser.error("Publication requires --public. Review the source before proceeding.")
    try:
        publish(args.owner, args.repo)
    except (OSError, ValueError, subprocess.TimeoutExpired, PublishError) as error:
        print(f"Publish stopped: {error}", file=sys.stderr)
        print("A late failure can leave a local commit or an empty/partially created remote. Review before retrying; this script never force-pushes.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
