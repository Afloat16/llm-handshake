import random
import unittest

from llm_handshake.sse import Event, SSEParser, StreamError


class SSETests(unittest.TestCase):
    def parse(self, body):
        parser = SSEParser()
        return parser.feed(body) + parser.finish()

    def test_basic(self):
        self.assertEqual(self.parse(b"data: hello\n\n"), [Event("hello")])

    def test_cr_lf_crlf(self):
        for separator in (b"\r", b"\n", b"\r\n"):
            with self.subTest(separator=separator):
                self.assertEqual(self.parse(separator.join([b"data: hello", b"", b""])), [Event("hello")])

    def test_multiline(self):
        self.assertEqual(self.parse(b"data: first\ndata:second\n\n"), [Event("first\nsecond")])

    def test_comments_and_unknown_fields(self):
        self.assertEqual(self.parse(b": hi\nid: 7\nretry: 2\nunknown: x\n\ndata: ok\n\n"), [Event("ok")])

    def test_empty_data_dispatch(self):
        self.assertEqual(self.parse(b"data:\n\ndata\n\n"), [Event(""), Event("")])

    def test_space_rule(self):
        self.assertEqual(self.parse(b"data:  hello\n\n"), [Event(" hello")])

    def test_event_type(self):
        self.assertEqual(self.parse(b"event: error\ndata: failed\n\n"), [Event("failed", "error")])

    def test_event_type_resets(self):
        self.assertEqual(self.parse(b"event: x\ndata: a\n\ndata: b\n\n"), [Event("a", "x"), Event("b")])

    def test_eof_does_not_dispatch(self):
        for body in (b"data: hello", b"data: hello\n", b"data: [DONE]\r\n"):
            with self.subTest(body=body):
                self.assertEqual(self.parse(body), [])

    def test_pending_frame(self):
        parser = SSEParser()
        parser.feed(b"data: partial\n")
        parser.finish()
        self.assertTrue(parser.pending)

    def test_bom_only_at_start(self):
        self.assertEqual(self.parse("\ufeffdata: 世界\n\n".encode()), [Event("世界")])

    def test_every_two_part_byte_split(self):
        body = "\ufeffdata: 你🙂\r\ndata: fine\r\n\r\ndata: [DONE]\n\n".encode()
        expected = [Event("你🙂\nfine"), Event("[DONE]")]
        for position in range(len(body) + 1):
            with self.subTest(position=position):
                parser = SSEParser()
                actual = parser.feed(body[:position]) + parser.feed(body[position:]) + parser.finish()
                self.assertEqual(actual, expected)

    def test_seeded_random_fragmentation(self):
        body = ("data: {\"text\":\"世界🙂\"}\r\n\r\n" * 10).encode()
        expected = self.parse(body)
        for seed in range(30):
            rng = random.Random(seed)
            parser = SSEParser()
            output = []
            at = 0
            while at < len(body):
                size = rng.randint(1, 17)
                output.extend(parser.feed(body[at:at + size]))
                at += size
            output.extend(parser.finish())
            self.assertEqual(output, expected)

    def test_invalid_utf8(self):
        with self.assertRaises(StreamError):
            self.parse(b"data: \xff\n\n")

    def test_truncated_utf8(self):
        with self.assertRaises(StreamError):
            self.parse(b"data: \xe4\xb8")

    def test_line_limit(self):
        with self.assertRaises(StreamError):
            SSEParser(max_chars=10).feed(b"data: abcdefghijkl")

    def test_event_limit_across_lines(self):
        with self.assertRaises(StreamError):
            SSEParser(max_chars=20).feed(b"data: 123456789\ndata: 123456789\ndata: z\n")

    def test_finish_is_idempotent(self):
        parser = SSEParser()
        self.assertEqual(parser.finish(), [])
        self.assertEqual(parser.finish(), [])
        with self.assertRaises(StreamError):
            parser.feed(b"x")
