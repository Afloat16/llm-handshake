import unittest
from unittest.mock import patch
from urllib.parse import SplitResult

from llm_handshake import Config, run_checks
from llm_handshake.config import PROBES, normalize_url, select_probes
from llm_handshake.plan import describe_plan, make_plan


class ConfigTests(unittest.TestCase):
    def test_https_prefix_preserved(self):
        self.assertEqual(normalize_url("https://EXAMPLE.test/gateway/v1///"), "https://example.test/gateway/v1")

    def test_no_v1_guessing(self):
        self.assertEqual(normalize_url("https://example.test"), "https://example.test")

    def test_loopback_http(self):
        for host in ("127.0.0.1", "127.0.0.2", "localhost", "[::1]"):
            with self.subTest(host=host):
                self.assertTrue(normalize_url(f"http://{host}:8000/v1").startswith("http:"))

    def test_plaintext_remote_requires_opt_in(self):
        with self.assertRaises(ValueError):
            normalize_url("http://example.test/v1")
        self.assertEqual(normalize_url("http://example.test/v1", True), "http://example.test/v1")

    def test_url_rejects_secret_bearing_parts(self):
        for value in ("https://a:b@host/v1", "https://host/v1?key=secret", "https://host/v1#secret", "https://@host", "https://host?"):
            with self.subTest(url=value), self.assertRaises(ValueError):
                normalize_url(value)

    def test_invalid_urls(self):
        for value in ("", "host/v1", "file:///etc/passwd", "https://", "https://bad host/v1", "https://host:0", "https://host:99999", "https://[invalid]/", "https://host\\evil", "https://中文/v1", "https://host/%0d%0Afoo", "https://host:bad", "https://bad|host"):
            with self.subTest(url=value), self.assertRaises(ValueError):
                normalize_url(value)

    def test_bracketed_host_validation_is_independent_of_parser_version(self):
        for authority in ("[invalid]", "[localhost]", "[127.0.0.1]", "[v1.example]"):
            parsed = SplitResult("https", authority, "/v1", "", "")
            with self.subTest(authority=authority), patch(
                "llm_handshake.config.urlsplit", return_value=parsed
            ), self.assertRaises(ValueError):
                normalize_url("https://" + authority + "/v1")

    def test_bracketed_authority_rejects_surrounding_text(self):
        for authority in ("prefix[::1]", "[::1]suffix", "[::1]:"):
            parsed = SplitResult("https", authority, "/v1", "", "")
            with self.subTest(authority=authority), patch(
                "llm_handshake.config.urlsplit", return_value=parsed
            ), self.assertRaises(ValueError):
                normalize_url("https://" + authority + "/v1")

    def test_full_routes_rejected(self):
        for path in ("/v1/models", "/chat/completions", "/v1/responses"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "base URL"):
                normalize_url("https://example.test" + path)

    def test_origin_omits_base_path(self):
        c = Config("https://example.test/tenant/private/v1")
        self.assertEqual(c.origin, "https://example.test")

    def test_config_repr_omits_credential_and_path(self):
        c = Config("https://example.test/secretpath", api_key="my-test-token")
        self.assertNotIn("my-test-token", repr(c))
        self.assertNotIn("secretpath", repr(c))

    def test_key_validation(self):
        for key in ("bad\r\nX: y", "has space", "中文", "a" * 8193):
            with self.subTest(key_length=len(key)), self.assertRaises(ValueError):
                Config("https://example.test", api_key=key)

    def test_model_validation(self):
        for model in ("x\n", "x" * 257, None):
            with self.subTest(model_type=type(model)), self.assertRaises(ValueError):
                Config("https://example.test", model=model)

    def test_timeout_bounds(self):
        for value in (0, -1, True, float("nan"), float("inf"), 301, "20"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Config("https://example.test", timeout=value)

    def test_numeric_limits(self):
        for key, values in (("max_requests", (0, 33, True)), ("max_output_tokens", (0, 4097, False)), ("max_response_bytes", (127, 8_388_609, 1.5))):
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    Config("https://example.test", **{key: value})

    def test_missing_model_for_inference(self):
        with self.assertRaises(ValueError):
            Config("https://example.test", probes=("chat",))

    def test_selection_canonical_order(self):
        self.assertEqual(select_probes("json, models,chat"), ("models", "chat", "json"))
        self.assertEqual(select_probes("all"), PROBES)

    def test_invalid_selection(self):
        for value in ("", "wat", "models,", "chat,chat"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_probes(value)

    def test_config_tuple_required(self):
        for probes in ([], (), ("unknown",), ("models", "models")):
            with self.subTest(probes=probes), self.assertRaises(ValueError):
                Config("https://example.test", probes=probes)

    def test_invalid_token_field(self):
        with self.assertRaises(ValueError):
            Config("https://example.test", token_limit_field="max_output_tokens")

    def test_plan_limit_checked_before_transport(self):
        with self.assertRaises(ValueError):
            Config("https://example.test", "m", probes=PROBES, max_requests=6)

    def test_consent_checked_before_transport(self):
        with patch("llm_handshake.runner.Transport") as transport:
            with self.assertRaisesRegex(ValueError, "Inference is disabled"):
                run_checks(Config("https://example.test", "m", probes=("chat",)))
            transport.assert_not_called()

    def test_target_fingerprint_ignores_key(self):
        a = Config("https://example.test/v1", "m", api_key="one")
        b = Config("https://example.test/v1/", "m", api_key="two")
        self.assertEqual(a.target_id, b.target_id)
        self.assertNotEqual(a.target_id, Config("https://example.test/v2", "m").target_id)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.config = Config("https://example.test/v1", "m", probes=PROBES)

    def test_seven_requests_six_inference(self):
        plan = describe_plan(self.config)
        self.assertEqual(plan["request_count"], 7)
        self.assertEqual(plan["inference_requests"], 6)
        self.assertEqual(plan["requested_output_token_ceiling"], 768)

    def test_stream_and_usage_are_isolated(self):
        specs = {s.name: s for s in make_plan(self.config)}
        self.assertNotIn("stream_options", specs["stream"].payload)
        self.assertEqual(specs["stream-usage"].payload["stream_options"], {"include_usage": True})

    def test_output_limit_field_not_silently_retried(self):
        config = Config("https://example.test", "m", probes=("chat",), token_limit_field="max_completion_tokens", max_output_tokens=64)
        payload = make_plan(config)[0].payload
        self.assertEqual(payload["max_completion_tokens"], 64)
        self.assertNotIn("max_tokens", payload)

    def test_tools_forced_without_execution(self):
        specs = {s.name: s for s in make_plan(self.config)}
        self.assertEqual(specs["tools"].payload["tool_choice"]["function"]["name"], "handshake_echo")
        self.assertTrue(specs["tool-stream"].streaming)

    def test_json_schema_is_narrow(self):
        body = make_plan(self.config)[-1].payload
        schema = body["response_format"]["json_schema"]
        self.assertTrue(schema["strict"])
        self.assertFalse(schema["schema"]["additionalProperties"])

    def test_default_plan_never_infers(self):
        specs = make_plan(Config("https://example.test"))
        self.assertEqual([(s.method, s.path, s.payload) for s in specs], [("GET", "/models", None)])
