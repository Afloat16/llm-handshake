"""Real local TLS handshakes. Certificates are ephemeral and never committed."""
import shutil
import ssl
import subprocess
import tempfile
import unittest
from pathlib import Path

from llm_handshake import Config
from llm_handshake.plan import make_plan
from llm_handshake.transport import Transport, TransportError
from helpers import endpoint


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL CLI is needed for ephemeral TLS fixtures")
class LocalTLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        cls.cert, cls.key = base / "cert.pem", base / "key.pem"
        config = base / "openssl.cnf"
        config.write_text("""[req]
prompt = no
distinguished_name = dn
x509_extensions = ext
[dn]
CN = handshake-loopback
[ext]
basicConstraints = critical,CA:TRUE
keyUsage = critical,digitalSignature,keyEncipherment,keyCertSign
subjectAltName = IP:127.0.0.1
""", encoding="utf-8")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(cls.key), "-out", str(cls.cert), "-days", "1",
                        "-config", str(config)], check=True, capture_output=True, timeout=30)
        cls.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.context.load_cert_chain(cls.cert, cls.key)

    def test_additional_ca_accepts_matching_loopback_certificate(self):
        with endpoint(ssl_context=self.context) as (base, records):
            config = Config(base, ca_file=str(self.cert))
            response = Transport(config).request(make_plan(config)[0])
        self.assertEqual(response.status, 200)
        self.assertEqual(len(records), 1)

    def test_default_trust_rejects_self_signed_certificate(self):
        with endpoint(ssl_context=self.context) as (base, records):
            config = Config(base)
            with self.assertRaises(TransportError) as caught:
                Transport(config).request(make_plan(config)[0])
        self.assertEqual(caught.exception.code, "tls_error")
        self.assertEqual(records, [])

    def test_added_ca_does_not_disable_hostname_verification(self):
        with endpoint(ssl_context=self.context) as (base, records):
            config = Config(base.replace("127.0.0.1", "localhost"), ca_file=str(self.cert))
            with self.assertRaises(TransportError) as caught:
                Transport(config).request(make_plan(config)[0])
        self.assertEqual(caught.exception.code, "tls_error")
        self.assertEqual(records, [])
