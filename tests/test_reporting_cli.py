import contextlib
import copy
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from llm_handshake import Config, run_checks
from llm_handshake.cli import main
from llm_handshake.mock import mock_server
from llm_handshake.models import ProbeResult
from llm_handshake.reporting import (clean_text, compare, gate, read_report, render,
                                    render_comparison, scrub, validate_report, write_private)


def sample():
    return {
        "schema": "llm-handshake.report.v1", "tool_version": "0.1.0", "mode": "live", "created_at": "2026-09-30T00:00:00+00:00",
        "target": {"id": "a" * 64, "origin": "https://example.test", "model": "test-model"},
        "contract": {"suite_version": 1, "token_limit_field": "max_tokens", "max_output_tokens": 128},
        "plan": {"probes": ["chat"], "max_requests": 7, "timeout_seconds": 20, "max_response_bytes": 1048576},
        "summary": {"pass": 1, "warn": 0, "fail": 0, "skip": 0},
        "requests_attempted": 1, "inference_requests_attempted": 1,
        "results": [ProbeResult("chat").to_dict()],
    }


def invoke(argv, env=None):
    output, error = io.StringIO(), io.StringIO()
    # Isolate application settings, not the operating system. Windows runtimes
    # can require SystemRoot and other platform variables during local I/O.
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("OPENAI_", "HANDSHAKE_")) and key != "MY_KEY"}
    environment.update(env or {})
    with patch.dict(os.environ, environment, clear=True), contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
        try:
            status = main(argv)
        except SystemExit as exception:
            status = exception.code
    return status, output.getvalue(), error.getvalue()


class ReportTests(unittest.TestCase):
    def test_gate_pass(self):
        self.assertEqual(gate(sample()), 0)

    def test_warning_gate(self):
        data = sample()
        data["results"][0]["status"] = "warn"
        self.assertEqual(gate(data), 0)
        self.assertEqual(gate(data, strict=True), 1)
        self.assertEqual(gate(data, required=("chat",)), 1)

    def test_required_missing(self):
        self.assertEqual(gate(sample(), required=("tools",)), 1)

    def test_unknown_required(self):
        with self.assertRaises(ValueError):
            gate(sample(), required=("unknown",))

    def test_fail_gate(self):
        data = sample()
        data["results"][0]["status"] = "fail"
        self.assertEqual(gate(data), 1)

    def test_skip_strict_gate(self):
        data = sample()
        data["results"][0]["status"] = "skip"
        self.assertEqual(gate(data, strict=True), 1)

    def test_unchanged_comparison(self):
        self.assertEqual(compare(sample(), sample())["changes"], [])

    def test_regression(self):
        after = sample()
        after["results"][0]["status"] = "warn"
        self.assertEqual(compare(sample(), after)["regressions"], 1)

    def test_improvement(self):
        before = sample()
        before["results"][0]["status"] = "fail"
        self.assertEqual(compare(before, sample())["changes"][0]["kind"], "improvement")

    def test_removed_probe_cannot_hide_regression(self):
        before = sample()
        before["results"].append(ProbeResult("tools").to_dict())
        comparison = compare(before, sample())
        self.assertEqual(comparison["regressions"], 1)
        self.assertEqual(comparison["changes"][0]["after"], "missing")

    def test_added_probe(self):
        after = sample()
        after["results"].append(ProbeResult("tools").to_dict())
        self.assertEqual(compare(sample(), after)["changes"][0]["kind"], "added")

    def test_target_changes_require_opt_in(self):
        after = sample()
        after["target"]["id"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "Targets differ"):
            compare(sample(), after)
        self.assertFalse(compare(sample(), after, True)["same_target"])

    def test_contract_changes_are_not_comparable(self):
        for key, value in (("suite_version", 2), ("max_output_tokens", 64), ("token_limit_field", "max_completion_tokens")):
            after = sample()
            after["contract"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "contracts differ"):
                compare(sample(), after)

    def test_duplicate_probes_rejected(self):
        data = sample()
        data["results"] *= 2
        with self.assertRaises(ValueError):
            validate_report(data)

    def test_invalid_report_boundary(self):
        variants = []
        for key, value in (("schema", "other"), ("target", {}), ("contract", {}), ("results", []), ("results", [{"name": "bad", "status": "pass"}])):
            data = sample()
            data[key] = value
            variants.append(data)
        for key, value in (("suite_version", True), ("max_output_tokens", 0), ("token_limit_field", "weird")):
            data = sample()
            data["contract"][key] = value
            variants.append(data)
        for data in variants:
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_report(data)

    def test_read_write_roundtrip_and_private_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            write_private(path, json.dumps(sample()))
            self.assertEqual(read_report(path), sample())
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_atomic_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text("before")
            write_private(path, "after")
            self.assertEqual(path.read_text(), "after")
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_symlink_output_not_followed(self):
        if os.name == "nt":
            self.skipTest("Symlink creation may need extra Windows privileges.")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "original").write_text("keep")
            (root / "report").symlink_to(root / "original")
            write_private(root / "report", "new")
            self.assertEqual((root / "original").read_text(), "keep")
            self.assertFalse((root / "report").is_symlink())

    def test_report_read_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            for body in (b"x" * 2097153, b"{bad", b"\xff"):
                path.write_bytes(body)
                with self.assertRaises(ValueError):
                    read_report(path)

    def test_render_all_formats(self):
        data = sample()
        self.assertIn("PASS", render(data))
        self.assertIn("| chat | PASS |", render(data, "markdown"))
        self.assertEqual(json.loads(render(data, "json")), data)
        with self.assertRaises(ValueError):
            render(data, "bad")

    def test_markdown_and_terminal_escaping(self):
        data = sample()
        data["results"][0]["findings"] = [{"status": "warn", "code": "x", "message": "<script>|`bad`\x1b\u202e", "hint": "Check <this>", "path": ""}]
        self.assertNotIn("<script>", render(data, "markdown"))
        self.assertNotIn("\x1b", render(data))
        self.assertNotIn("\u202e", render(data))

    def test_scrub_configured_token(self):
        self.assertEqual(scrub({"key": ["the-secret"]}, "the-secret"), {"key": ["[REDACTED]"]})

    def test_comparison_formats(self):
        data = compare(sample(), sample())
        self.assertIn("No probe-status changes", render_comparison(data))
        self.assertEqual(json.loads(render_comparison(data, "json")), data)
        self.assertTrue(render_comparison(data, "markdown").startswith("# "))

    def test_invalid_finding_status(self):
        with self.assertRaises(ValueError):
            ProbeResult("chat").add("mystery", "x", "x")


class CLITests(unittest.TestCase):
    def test_invocation_preserves_system_settings_not_provider_settings(self):
        observed = {}

        def capture(argv):
            observed.update(os.environ)
            return 0

        with patch.dict(os.environ, {"SystemRoot": "system-root-sentinel", "OPENAI_API_KEY": "ambient-key"}):
            with patch(__name__ + ".main", side_effect=capture):
                status, _, _ = invoke(["--version"])
        self.assertEqual(status, 0)
        self.assertEqual({key.upper(): value for key, value in observed.items()}["SYSTEMROOT"], "system-root-sentinel")
        self.assertNotIn("OPENAI_API_KEY", observed)

    def test_help(self):
        status, output, _ = invoke(["--help"])
        self.assertEqual(status, 0)
        self.assertIn("compare", output)

    def test_version(self):
        self.assertEqual(invoke(["--version"])[1].strip(), "llm-handshake 0.1.0")

    def test_argument_error_does_not_echo_token(self):
        status, output, error = invoke(["--api-key", "private-sentinel"])
        self.assertEqual(status, 2)
        self.assertNotIn("private-sentinel", output + error)

    def test_missing_base_has_actionable_error(self):
        status, _, error = invoke(["check"])
        self.assertEqual(status, 2)
        self.assertIn("--base-url", error)

    def test_plan_is_network_free(self):
        with patch("llm_handshake.runner.Transport") as transport:
            status, output, _ = invoke(["plan", "--base-url", "https://example.test/v1", "--model", "m", "--probes", "all", "--format", "json"])
        transport.assert_not_called()
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)["inference_requests"], 6)

    def test_plan_formats(self):
        for format in ("text", "markdown"):
            with self.subTest(format=format):
                status, output, _ = invoke(["plan", "--base-url", "https://example.test/v1", "--format", format])
                self.assertEqual(status, 0)
                self.assertIn("/models", output)

    def test_inference_requires_consent(self):
        status, _, error = invoke(["check", "--base-url", "https://example.test", "--model", "m", "--probes", "chat"])
        self.assertEqual(status, 2)
        self.assertIn("--allow-inference", error)

    def test_require_must_be_selected_before_io(self):
        status, _, error = invoke(["check", "--base-url", "https://example.test", "--require", "chat"])
        self.assertEqual(status, 2)
        self.assertIn("--probes", error)

    def test_env_configuration(self):
        with mock_server() as base:
            status, output, _ = invoke(["check", "--format", "json"], {"OPENAI_BASE_URL": base, "OPENAI_MODEL": "handshake-demo"})
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)["summary"]["pass"], 1)

    def test_custom_key_variable_and_no_auth(self):
        from helpers import endpoint
        with endpoint(body=b'{"data":[]}') as (base, records):
            status, _, _ = invoke(["check", "--base-url", base, "--api-key-env", "MY_KEY", "--no-auth"], {"MY_KEY": "secret"})
        self.assertEqual(status, 0)
        self.assertIsNone(records[0]["authorization"])

    def test_demo_ignores_external_environment(self):
        status, output, error = invoke(["demo", "--format", "json"], {"OPENAI_BASE_URL": "https://example.test", "OPENAI_API_KEY": "sentinel"})
        self.assertEqual(status, 0)
        self.assertEqual(error, "")
        self.assertEqual(json.loads(output)["mode"], "demo")
        self.assertNotIn("sentinel", output)

    def test_broken_demo_exit(self):
        status, output, _ = invoke(["demo", "--broken"])
        self.assertEqual(status, 1)
        self.assertIn("4 pass / 1 warn / 2 fail", output)

    def test_output_file_and_no_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            status, output, _ = invoke(["demo", "--format", "json", "--output", str(path)])
            self.assertEqual(status, 0)
            self.assertEqual(output, "")
            self.assertEqual(read_report(path)["mode"], "demo")

    def test_bad_output_path(self):
        status, _, error = invoke(["plan", "--base-url", "https://example.test", "--output", "/not/a/real/path/report.json"])
        self.assertEqual(status, 2)
        self.assertIn("local file", error)

    def test_compare_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.json", Path(directory) / "b.json"
            data = sample()
            a.write_text(json.dumps(data))
            b.write_text(json.dumps(data))
            self.assertEqual(invoke(["compare", str(a), str(b)])[0], 0)
            data["results"][0]["status"] = "fail"
            b.write_text(json.dumps(data))
            status, output, _ = invoke(["compare", str(a), str(b), "--format", "json"])
            self.assertEqual(status, 3)
            self.assertEqual(json.loads(output)["regressions"], 1)

    def test_compare_missing_file(self):
        self.assertEqual(invoke(["compare", "missing.json", "other.json"])[0], 2)

    def test_keyboard_interrupt(self):
        with patch("llm_handshake.cli.run_checks", side_effect=KeyboardInterrupt):
            status, _, error = invoke(["check", "--base-url", "https://example.test"])
        self.assertEqual(status, 130)
        self.assertIn("interrupted", error)

    def test_plan_redacts_model_matching_key(self):
        status, output, _ = invoke(["plan", "--base-url", "https://example.test", "--model", "my-secret", "--probes", "chat", "--format", "json"], {"OPENAI_API_KEY": "my-secret"})
        self.assertEqual(status, 0)
        self.assertNotIn("my-secret", output)
        self.assertEqual(json.loads(output)["schema"], "llm-handshake.plan.v1")
