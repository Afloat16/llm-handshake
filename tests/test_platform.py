"""Regression tests for platform boundaries identified by the CI matrix."""
import unittest
from unittest.mock import patch

from llm_handshake import Config
from llm_handshake.mock import mock_server
from llm_handshake.plan import make_plan
from llm_handshake.transport import Transport, TransportError
from helpers import endpoint


class PlatformBoundaryTests(unittest.TestCase):
    def test_demo_server_never_queries_reverse_dns(self):
        with patch("socket.getfqdn", side_effect=AssertionError("Unexpected reverse DNS")):
            with mock_server() as base:
                config = Config(base)
                response = Transport(config).request(make_plan(config)[0])
        self.assertEqual(response.status, 200)

    def test_fixture_server_never_queries_reverse_dns(self):
        with patch("socket.getfqdn", side_effect=AssertionError("Unexpected reverse DNS")):
            with endpoint() as (base, records):
                config = Config(base)
                response = Transport(config).request(make_plan(config)[0])
        self.assertEqual(response.status, 200)
        self.assertEqual(len(records), 1)

    def test_explicit_connection_refusal_is_classified_without_retry(self):
        config = Config("http://127.0.0.1:1/v1")
        with patch("llm_handshake.transport.http.client.HTTPConnection") as connection:
            connection.return_value.request.side_effect = ConnectionRefusedError()
            with self.assertRaises(TransportError) as caught:
                Transport(config).request(make_plan(config)[0])
            self.assertEqual(connection.return_value.request.call_count, 1)
        self.assertEqual(caught.exception.code, "connection_error")
