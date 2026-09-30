import json
import os
import socket
import ssl
import time
import unittest
from unittest.mock import patch

from llm_handshake import Config, run_checks
from llm_handshake.config import PROBES
from llm_handshake.mock import completion, encode_stream, mock_server, stream_chunks
from llm_handshake.plan import make_plan
from llm_handshake.runner import failure
from llm_handshake.transport import Transport, TransportError
from helpers import codes, endpoint


class TransportTests(unittest.TestCase):
    def request(self, base, probes=("models",), **kwargs):
        config = Config(base, "handshake-demo", probes=probes, **kwargs)
        return Transport(config).request(make_plan(config)[0])

    def test_get_route_prefix_and_no_auth(self):
        with endpoint() as (base, records):
            result = self.request(base)
        self.assertEqual(result.status, 200)
        self.assertEqual(records[0]["path"], "/v1/models")
        self.assertIsNone(records[0]["authorization"])

    def test_post_serialization_and_bearer_header(self):
        with endpoint(body=json.dumps(completion()).encode()) as (base, records):
            self.request(base, probes=("chat",), api_key="test-token")
        self.assertEqual(records[0]["authorization"], "Bearer test-token")
        payload = json.loads(records[0]["body"])
        self.assertEqual(payload["max_tokens"], 128)
        self.assertEqual(payload["model"], "handshake-demo")

    def test_stream_receives_events(self):
        with endpoint(body=encode_stream(stream_chunks()), mime="text/event-stream") as (base, _):
            result = self.request(base, probes=("stream",))
        self.assertEqual(result.events[-1][0].data, "[DONE]")
        self.assertEqual(result.body, b"")

    def test_json_suffix_content_type(self):
        with endpoint(mime="application/problem+json") as (base, _):
            self.assertEqual(self.request(base).status, 200)

    def test_bad_content_type(self):
        for mime in ("text/html", None, "nonsense+json"):
            with self.subTest(mime=mime), endpoint(mime=mime) as (base, _):
                with self.assertRaises(TransportError) as error:
                    self.request(base)
                self.assertEqual(error.exception.code, "content_type")

    def test_compression_is_not_accepted(self):
        with endpoint(headers={"Content-Encoding": "gzip"}) as (base, _):
            with self.assertRaises(TransportError) as error:
                self.request(base)
        self.assertEqual(error.exception.code, "content_encoding")

    def test_announced_response_limit(self):
        with endpoint(declared_length=99999) as (base, _):
            with self.assertRaises(TransportError) as error:
                self.request(base, max_response_bytes=128)
        self.assertEqual(error.exception.code, "response_limit")

    def test_unannounced_response_limit(self):
        with endpoint(body=b"x" * 300, omit_length=True) as (base, _):
            with self.assertRaises(TransportError) as error:
                self.request(base, max_response_bytes=128)
        self.assertEqual(error.exception.code, "response_limit")

    def test_invalid_content_length(self):
        for value in ("abc", -1):
            with self.subTest(value=value), endpoint(declared_length=value) as (base, _):
                with self.assertRaises(TransportError) as error:
                    self.request(base)
                self.assertEqual(error.exception.code, "invalid_content_length")

    def test_truncated_json_body(self):
        with endpoint(declared_length=100) as (base, _):
            with self.assertRaises(TransportError) as error:
                self.request(base)
        self.assertEqual(error.exception.code, "truncated_body")

    def test_no_redirect_or_credential_forwarding(self):
        with endpoint() as (target, received):
            with endpoint(status=307, headers={"Location": target}) as (base, sent):
                with self.assertRaises(TransportError) as error:
                    self.request(base, api_key="test-token")
        self.assertEqual(error.exception.http_status, 307)
        self.assertEqual(len(sent), 1)
        self.assertEqual(received, [])

    def test_error_body_never_exposed(self):
        with endpoint(body=b"TOP-SECRET-PROVIDER-ECHO", status=401) as (base, _):
            with self.assertRaises(TransportError) as error:
                self.request(base)
        self.assertNotIn("TOP-SECRET", str(error.exception))

    def test_no_proxy_environment_usage(self):
        with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1"}):
            with endpoint() as (base, _):
                self.assertEqual(self.request(base).status, 200)

    def test_timeout_on_stalled_body(self):
        with endpoint(delay=0.5) as (base, _):
            started = time.monotonic()
            with self.assertRaises(TransportError) as error:
                self.request(base, timeout=0.06)
            elapsed = time.monotonic() - started
        self.assertEqual(error.exception.code, "timeout")
        self.assertLess(elapsed, 0.45)

    def test_drip_cannot_reset_deadline(self):
        with endpoint(body=b"{" + b" " * 100, drip=True, delay=0.01) as (base, _):
            started = time.monotonic()
            with self.assertRaises(TransportError) as error:
                self.request(base, timeout=0.08)
            elapsed = time.monotonic() - started
        self.assertEqual(error.exception.code, "timeout")
        self.assertLess(elapsed, 0.5)

    def test_invalid_stream_utf8(self):
        with endpoint(body=b"data: \xff\n\n", mime="text/event-stream") as (base, _):
            with self.assertRaises(TransportError) as error:
                self.request(base, probes=("stream",))
        self.assertEqual(error.exception.code, "sse_framing")

    def test_event_count_is_bounded(self):
        with endpoint(body=b"data: {}\n\n" * 4100, mime="text/event-stream") as (base, _):
            with self.assertRaises(TransportError) as error:
                self.request(base, probes=("stream",))
        self.assertEqual(error.exception.code, "event_limit")

    def test_refused_connection(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            # Bound but deliberately not listening; another process cannot claim it.
            with self.assertRaises(TransportError) as error:
                self.request(f"http://127.0.0.1:{port}/v1")
        self.assertEqual(error.exception.code, "connection_error")

    def test_invalid_ca_sends_nothing(self):
        with patch("llm_handshake.transport.http.client.HTTPSConnection") as connection:
            with self.assertRaises(ValueError):
                Transport(Config("https://example.test", ca_file="/path/that/does/not/exist"))
            connection.assert_not_called()

    def test_tls_verification_remains_enabled(self):
        transport = Transport(Config("https://example.test"))
        self.assertEqual(transport._ssl.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(transport._ssl.check_hostname)

    def test_tls_errors_classified(self):
        with patch("llm_handshake.transport.http.client.HTTPSConnection") as connection:
            connection.return_value.request.side_effect = ssl.SSLError("sensitive detail")
            with self.assertRaises(TransportError) as error:
                self.request("https://example.test/v1")
        self.assertEqual(error.exception.code, "tls_error")
        self.assertNotIn("sensitive", str(error.exception))


class RunnerTests(unittest.TestCase):
    def test_full_healthy_demo(self):
        with mock_server() as base:
            report = run_checks(Config(base, "handshake-demo", probes=PROBES, allow_inference=True))
        self.assertEqual(report["summary"], {"pass": 7, "warn": 0, "fail": 0, "skip": 0})
        self.assertEqual(report["requests_attempted"], 7)
        self.assertEqual(report["inference_requests_attempted"], 6)

    def test_broken_demo_separates_failures(self):
        with mock_server(True) as base:
            report = run_checks(Config(base, "handshake-demo", probes=PROBES, allow_inference=True))
        statuses = {r["name"]: r["status"] for r in report["results"]}
        self.assertEqual(statuses["stream"], "pass")
        self.assertEqual(statuses["stream-usage"], "warn")
        self.assertEqual(statuses["tool-stream"], "fail")
        self.assertEqual(statuses["json"], "fail")

    def test_auth_and_quota_fail_fast(self):
        for status in (401, 403, 429, 500, 503):
            with self.subTest(status=status), endpoint(status=status) as (base, records):
                report = run_checks(Config(base, "handshake-demo", probes=PROBES, allow_inference=True))
            self.assertEqual(len(records), 1)
            self.assertEqual(report["summary"]["skip"], 6)
            self.assertEqual(report["requests_attempted"], 1)

    def test_models_404_does_not_block_other_probes(self):
        with endpoint(status=404) as (base, records):
            report = run_checks(Config(base, "m", probes=("models", "chat"), allow_inference=True))
        self.assertEqual(len(records), 2)
        self.assertEqual([r["status"] for r in report["results"]], ["warn", "fail"])

    def test_bad_optional_request_is_not_retried(self):
        with endpoint(status=400) as (base, records):
            report = run_checks(Config(base, "m", probes=("stream-usage",), allow_inference=True))
        self.assertEqual(len(records), 1)
        self.assertEqual(report["summary"]["fail"], 1)

    def test_model_and_origin_redact_known_key(self):
        with endpoint(body=b'{"data":[]}') as (base, _):
            report = run_checks(Config(base, "model-test-key", api_key="test-key"))
        dumped = json.dumps(report)
        self.assertNotIn("test-key", dumped)
        self.assertIn("[REDACTED]", dumped)

    def test_short_dummy_key_does_not_corrupt_schema(self):
        with endpoint() as (base, _):
            report = run_checks(Config(base, api_key="1"))
        self.assertEqual(report["schema"], "llm-handshake.report.v1")
        self.assertEqual(report["results"][0]["name"], "models")

    def test_raw_response_not_retained(self):
        body = json.dumps(completion("PRIVATE-PROVIDER-CONTENT")).encode()
        with endpoint(body=body) as (base, _):
            report = run_checks(Config(base, "m", probes=("chat",), allow_inference=True))
        self.assertNotIn("PRIVATE-PROVIDER-CONTENT", json.dumps(report))

    def test_http_classification_is_cautious(self):
        expectations = [(302, "redirect_blocked"), (401, "authentication"), (429, "rate_limited"),
                        (404, "route_or_model_missing"), (422, "request_rejected"),
                        (502, "upstream_error"), (418, "http_error")]
        for status, code in expectations:
            with self.subTest(status=status):
                self.assertIn(code, codes(failure("chat", TransportError("http_status", status))))

    def test_unknown_transport_failure_has_safe_message(self):
        result = failure("chat", TransportError("future_code"))
        self.assertEqual(result.status, "fail")
