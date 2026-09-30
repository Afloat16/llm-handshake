import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location("handshake_script_" + name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = script("build_zipapp")
publisher = script("publish")


class BuildTests(unittest.TestCase):
    def test_reproducible_archive_and_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            one, two = Path(directory) / "a.pyz", Path(directory) / "b.pyz"
            digest = builder.build(one)
            self.assertEqual(digest, builder.build(two))
            self.assertEqual(one.read_bytes(), two.read_bytes())
            self.assertEqual(hashlib.sha256(one.read_bytes()).hexdigest(), digest)
            self.assertIn(digest, one.with_suffix(".pyz.sha256").read_text())

    def test_archive_contains_only_runtime_source_and_license(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "app.pyz"
            builder.build(target)
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                self.assertIn("LICENSE", names)
                self.assertIn("__main__.py", names)
                self.assertIn("llm_handshake/cli.py", names)
                self.assertTrue(all(name in ("LICENSE", "__main__.py") or name.startswith("llm_handshake/") for name in names))
                self.assertFalse(any("__pycache__" in name for name in names))

    def test_isolated_executable_needs_no_provider_or_package_install(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "app.pyz"
            builder.build(target)
            env = os.environ.copy()
            env.update(OPENAI_BASE_URL="https://must-not-contact.invalid", OPENAI_API_KEY="NEVER-SEND-THIS")
            result = subprocess.run([sys.executable, "-I", str(target), "demo", "--strict", "--format", "json"],
                                    capture_output=True, text=True, check=True, timeout=20, cwd=directory, env=env)
            report = json.loads(result.stdout)
            self.assertEqual(report["summary"]["pass"], 7)
            self.assertEqual(report["mode"], "demo")
            self.assertNotIn("NEVER-SEND-THIS", result.stdout + result.stderr)

    def test_missing_runtime_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "LICENSE").write_text("test")
            with self.assertRaises(ValueError):
                builder.build(root / "app.pyz", root)


class PublicationSafetyTests(unittest.TestCase):
    def test_owner_must_match_authenticated_account(self):
        with self.assertRaises(publisher.PublishError):
            publisher.validate_identity("Owner", "llm-handshake", {"login": "Other", "id": 1})

    def test_case_insensitive_valid_owner(self):
        publisher.validate_identity("Owner", "llm-handshake", {"login": "owner", "id": 1})

    def test_invalid_names_rejected(self):
        for owner, repo in (("--owner", "x"), ("owner", "../x"), ("owner", "x.git"), ("owner", "--x")):
            with self.subTest(owner=owner, repo=repo), self.assertRaises(publisher.PublishError):
                publisher.validate_identity(owner, repo, {"login": owner, "id": 1})

    def test_selection_omits_secrets_and_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("README.md", "README.zh-CN.md", "LICENSE", "pyproject.toml", ".env", "private.key"):
                (root / name).write_text("test")
            for name in ("src/llm_handshake/__init__.py", "tests/test_ok.py", "docs/notes.md", "docs/private.pem",
                         "dist/app.pyz", "reports/private.json", ".git/config", "src/llm_handshake/__pycache__/x.pyc"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test")
            selected = publisher.selected_files(root)
            self.assertIn("src/llm_handshake/__init__.py", selected)
            self.assertIn("docs/notes.md", selected)
            self.assertFalse(any(name in selected for name in (".env", "private.key", "docs/private.pem", "reports/private.json", "dist/app.pyz")))
            self.assertFalse(any(".git/" in name or "__pycache__" in name for name in selected))

    def test_required_files_are_required(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(publisher.PublishError):
            publisher.selected_files(Path(directory))

    def test_only_confirmed_404_allows_initial_creation(self):
        result = subprocess.CompletedProcess([], 1, "HTTP/2.0 404 Not Found\n{}", "")
        with patch.object(publisher, "run", return_value=result):
            publisher.require_new_repo("owner", "repo")

    def test_existing_repo_auth_errors_and_network_errors_stop(self):
        for text in ("HTTP/2.0 200 OK\n{}", "HTTP/2.0 403 Forbidden\n{}", "HTTP/2.0 500 Internal Server Error\n{}", ""):
            with self.subTest(text=text), patch.object(publisher, "run", return_value=subprocess.CompletedProcess([], 1, text, "")):
                with self.assertRaises(publisher.PublishError):
                    publisher.require_new_repo("owner", "repo")

    def test_auth_host_is_explicit_and_ambient_repo_is_ignored(self):
        with patch.dict(os.environ, {"GH_HOST": "other.invalid", "GH_REPO": "other/repo"}):
            with patch.object(publisher.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as invoked:
                publisher.run(["gh", "api", "user"])
        environment = invoked.call_args.kwargs["env"]
        self.assertEqual(environment["GH_HOST"], "github.com")
        self.assertNotIn("GH_REPO", environment)

    def test_git_directory_overrides_are_ignored(self):
        with patch.dict(os.environ, {"GIT_DIR": "other", "GIT_INDEX_FILE": "other-index"}):
            with patch.object(publisher.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as invoked:
                publisher.run(["git", "status"])
        self.assertNotIn("GIT_DIR", invoked.call_args.kwargs["env"])
        self.assertNotIn("GIT_INDEX_FILE", invoked.call_args.kwargs["env"])

    def test_failed_tool_output_does_not_echo_credentials(self):
        with patch.object(publisher.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "SECRET", "SECRET")):
            with self.assertRaises(publisher.PublishError) as caught:
                publisher.run(["git", "status"])
        self.assertNotIn("SECRET", str(caught.exception))

    def test_missing_gh_is_actionable(self):
        with patch.object(publisher.shutil, "which", return_value=None):
            with self.assertRaises(publisher.PublishError):
                publisher.publish("owner", "repo")

    def test_publication_requires_explicit_public_flag(self):
        with patch.object(sys, "argv", ["publish.py", "--owner", "owner"]), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                publisher.main()
        self.assertEqual(caught.exception.code, 2)

    def test_existing_local_history_is_not_published(self):
        def fake(args, **kwargs):
            if args[:3] == ["gh", "api", "user"]:
                return subprocess.CompletedProcess(args, 0, '{"login":"owner","id":1}', "")
            return subprocess.CompletedProcess(args, 0, str(ROOT), "")
        with patch.object(publisher.shutil, "which", return_value="/tool"), patch.object(publisher, "run", side_effect=fake), \
                patch.object(publisher, "selected_files", return_value=["README.md"]), patch.object(publisher, "require_new_repo"):
            with self.assertRaisesRegex(publisher.PublishError, "Git repository already"):
                publisher.publish("owner", "repo")
