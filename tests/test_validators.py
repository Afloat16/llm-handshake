import copy
import json
import unittest

from llm_handshake.mock import chunk, completion, stream_chunks
from llm_handshake.sse import Event
from llm_handshake.transport import WireResponse
from llm_handshake.validators import inspect, load_json
from helpers import CONFIG, codes, inspected, json_wire, stream_wire


class JSONValidationTests(unittest.TestCase):
    def test_chat_success(self):
        self.assertEqual(inspected().status, "pass")

    def test_envelope_required_fields(self):
        for key in ("id", "model", "created", "object"):
            data = completion()
            del data[key]
            with self.subTest(key=key):
                self.assertEqual(inspected(data).status, "fail")

    def test_boolean_is_not_timestamp(self):
        data = completion()
        data["created"] = True
        self.assertIn("envelope_created", codes(inspected(data)))

    def test_error_in_http_success(self):
        self.assertIn("response_error", codes(inspected({"error": {"message": "do not log"}})))

    def test_nonobject_completion(self):
        self.assertEqual(inspected([]).status, "fail")

    def test_choice_validation(self):
        for choices in (None, [], [{}, {}], ["bad"]):
            data = completion()
            data["choices"] = choices
            with self.subTest(choices=choices):
                self.assertIn("choices_shape", codes(inspected(data)))

    def test_choice_index(self):
        data = completion()
        data["choices"][0]["index"] = False
        self.assertIn("choice_index", codes(inspected(data)))

    def test_message_role(self):
        data = completion()
        data["choices"][0]["message"]["role"] = "system"
        self.assertIn("assistant_message", codes(inspected(data)))

    def test_missing_content(self):
        self.assertIn("content_missing", codes(inspected(completion(""))))

    def test_usage_missing_warn_not_zero(self):
        data = completion()
        del data["usage"]
        result = inspected(data)
        self.assertEqual(result.status, "warn")
        self.assertNotIn("total_tokens", result.metrics)

    def test_bad_usage_types(self):
        for value in ({}, "bad", {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2}, {"prompt_tokens": -1, "completion_tokens": 1, "total_tokens": 0}):
            data = completion()
            data["usage"] = value
            with self.subTest(value=value):
                self.assertIn("usage_shape", codes(inspected(data)))

    def test_usage_sum(self):
        data = completion()
        data["usage"]["total_tokens"] = 99
        self.assertIn("usage_sum", codes(inspected(data)))

    def test_length_is_inconclusive_not_unsupported(self):
        data = completion("")
        data["choices"][0]["finish_reason"] = "length"
        result = inspected(data)
        self.assertEqual(result.status, "warn")
        self.assertNotIn("content_missing", codes(result))

    def test_content_filter(self):
        data = completion("")
        data["choices"][0]["finish_reason"] = "content_filter"
        self.assertEqual(inspected(data).status, "warn")

    def test_refusal(self):
        data = completion("")
        data["choices"][0]["message"]["refusal"] = "No"
        self.assertIn("refusal", codes(inspected(data)))

    def test_unexpected_finish(self):
        data = completion()
        data["choices"][0]["finish_reason"] = None
        self.assertIn("finish_reason", codes(inspected(data)))

    def test_json_sample_success(self):
        self.assertEqual(inspected(completion('{"value":7}'), "json").status, "pass")

    def test_json_wrong_type_or_extra_fields(self):
        for value in ('{"value":"7"}', '{"value":true}', '{"value":7,"extra":1}', '```json\n{"value":7}\n```', '{"value":8}', '{}', 'broken'):
            with self.subTest(value=value):
                self.assertIn("json_schema_sample", codes(inspected(completion(value), "json")))

    def test_tool_success(self):
        self.assertEqual(inspected(completion(tool=True), "tools").status, "pass")

    def test_tool_shape(self):
        data = completion(tool=True)
        data["choices"][0]["message"]["tool_calls"] = []
        self.assertIn("tool_calls_shape", codes(inspected(data, "tools")))

    def test_tool_missing_id_and_type(self):
        data = completion(tool=True)
        call = data["choices"][0]["message"]["tool_calls"][0]
        del call["id"]
        call["type"] = "other"
        self.assertIn("tool_identity", codes(inspected(data, "tools")))

    def test_tool_wrong_name(self):
        data = completion(tool=True)
        data["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = "something_else"
        self.assertIn("tool_name", codes(inspected(data, "tools")))

    def test_tool_arguments_must_be_json_string(self):
        data = completion(tool=True)
        data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = {"value": 7}
        self.assertIn("tool_arguments", codes(inspected(data, "tools")))

    def test_tool_finish(self):
        data = completion(tool=True)
        data["choices"][0]["finish_reason"] = "stop"
        self.assertIn("tool_finish_reason", codes(inspected(data, "tools")))

    def test_models_shape(self):
        self.assertIn("models_shape", codes(inspected({"data": {}}, "models")))

    def test_models_invalid_ids(self):
        for entries in ([{}], [None], [{"id": ""}], [{"id": []}]):
            with self.subTest(entries=entries):
                self.assertIn("model_ids", codes(inspected({"data": entries}, "models")))

    def test_models_empty(self):
        self.assertIn("models_empty", codes(inspected({"data": []}, "models")))

    def test_model_not_listed_does_not_fail(self):
        result = inspected({"data": [{"id": "other"}]}, "models")
        self.assertEqual(result.status, "warn")
        self.assertNotIn("other", json.dumps(result.to_dict()))

    def test_model_duplicate(self):
        result = inspected({"data": [{"id": "handshake-demo"}] * 2}, "models")
        self.assertIn("duplicate_models", codes(result))

    def test_invalid_json_boundaries(self):
        for body in (b"not-json", b"\xff", b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":1e999}', b"1" * 21):
            with self.subTest(body=body):
                result = inspect("chat", WireResponse(200, body), CONFIG)
                self.assertIn("invalid_json", codes(result))

    def test_deep_json_is_reported(self):
        result = inspect("chat", WireResponse(200, b"[" * 2000 + b"]" * 2000), CONFIG)
        self.assertIn("invalid_json", codes(result))


class StreamValidationTests(unittest.TestCase):
    def result(self, parts=None, name="stream", done=True):
        return inspect(name, stream_wire(parts, done), CONFIG)

    def test_stream_success(self):
        self.assertEqual(self.result().status, "pass")

    def test_stream_usage_success(self):
        result = self.result(stream_chunks(include_usage=True), "stream-usage")
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.metrics["total_tokens"], 16)

    def test_stream_usage_missing_is_warn(self):
        self.assertEqual(self.result(name="stream-usage").status, "warn")
        self.assertEqual(self.result().status, "pass")

    def test_partial_tool_arguments_reassembled(self):
        self.assertEqual(self.result(stream_chunks(tool=True), "tool-stream").status, "pass")

    def test_malformed_tool_arguments(self):
        self.assertIn("tool_arguments", codes(self.result(stream_chunks(tool=True, broken=True), "tool-stream")))

    def test_done_required(self):
        self.assertIn("done_missing", codes(self.result(done=False)))

    def test_finish_required(self):
        self.assertIn("finish_missing", codes(self.result(stream_chunks()[:-1])))

    def test_stream_identity_consistency(self):
        parts = stream_chunks()
        parts[1]["id"] = "other"
        self.assertIn("stream_identity_changed", codes(self.result(parts)))

    def test_bad_chunk_envelope(self):
        parts = stream_chunks()
        del parts[0]["model"]
        self.assertIn("envelope_model", codes(self.result(parts)))

    def test_empty_choice_metadata_warn(self):
        parts = stream_chunks()
        parts.insert(1, chunk(usage_only=True))
        del parts[1]["usage"]
        self.assertIn("empty_stream_chunk", codes(self.result(parts)))

    def test_multiple_usage_chunks_not_summed(self):
        parts = stream_chunks(include_usage=True)
        parts.append(chunk(usage_only=True))
        result = self.result(parts, "stream-usage")
        self.assertIn("multiple_usage_chunks", codes(result))
        self.assertEqual(result.metrics["total_tokens"], 16)

    def test_missing_stream_choices(self):
        parts = stream_chunks()
        parts[0]["choices"] = None
        self.assertIn("stream_choices", codes(self.result(parts)))

    def test_choice_cardinality(self):
        parts = stream_chunks()
        parts[0]["choices"] *= 2
        self.assertIn("stream_choice_count", codes(self.result(parts)))

    def test_stream_choice_index(self):
        parts = stream_chunks()
        parts[0]["choices"][0]["index"] = 2
        self.assertIn("stream_choice_index", codes(self.result(parts)))

    def test_delta_must_be_object(self):
        parts = stream_chunks()
        parts[0]["choices"][0]["delta"] = None
        self.assertIn("stream_delta", codes(self.result(parts)))

    def test_data_after_finish(self):
        parts = stream_chunks()
        parts.append(chunk({"content": "late"}))
        self.assertIn("choice_after_finish", codes(self.result(parts)))

    def test_unknown_finish_reason(self):
        parts = stream_chunks()
        parts[-1]["choices"][0]["finish_reason"] = "weird"
        self.assertIn("stream_finish_reason", codes(self.result(parts)))

    def test_wrong_role(self):
        parts = stream_chunks()
        parts[0]["choices"][0]["delta"]["role"] = "user"
        self.assertIn("stream_role", codes(self.result(parts)))

    def test_missing_role_is_warning(self):
        self.assertIn("stream_role_missing", codes(self.result(stream_chunks()[1:])))

    def test_bad_content_type(self):
        parts = stream_chunks()
        parts[1]["choices"][0]["delta"]["content"] = ["wrong"]
        self.assertIn("stream_content_type", codes(self.result(parts)))

    def test_stream_refusal(self):
        parts = [chunk({"role": "assistant", "refusal": "No"}), chunk(finish="stop")]
        self.assertEqual(self.result(parts).status, "warn")

    def test_stream_empty_content(self):
        parts = [chunk({"role": "assistant"}), chunk(finish="stop")]
        self.assertIn("stream_content_missing", codes(self.result(parts)))

    def test_stream_truncation_inconclusive(self):
        parts = [chunk({"role": "assistant"}), chunk(finish="length")]
        self.assertEqual(self.result(parts).status, "warn")

    def test_bad_tool_fragment_shapes(self):
        mutations = [({}, "tool_delta_index"), ({"index": True}, "tool_delta_index"),
                     ({"index": 0, "function": []}, "tool_delta_function"),
                     ({"index": 0, "function": {"arguments": 7}}, "tool_delta_text"),
                     ({"index": 0, "id": "other"}, "tool_delta_identity")]
        for fragment, code in mutations:
            parts = stream_chunks(tool=True)
            parts.insert(2, chunk({"tool_calls": [fragment]}))
            with self.subTest(code=code):
                self.assertIn(code, codes(self.result(parts, "tool-stream")))

    def test_tool_calls_delta_is_array(self):
        parts = stream_chunks(tool=True)
        parts[1]["choices"][0]["delta"]["tool_calls"] = {}
        self.assertIn("tool_delta_shape", codes(self.result(parts, "tool-stream")))

    def test_tool_stream_finish(self):
        parts = stream_chunks(tool=True)
        parts[-1]["choices"][0]["finish_reason"] = "stop"
        self.assertIn("tool_finish_reason", codes(self.result(parts, "tool-stream")))

    def test_error_events_and_json_do_not_leak(self):
        wire = WireResponse(200, events=[(Event("SECRET", "error"), 1),
                                        (Event("SECRET"), 2), (Event('{"error":"SECRET"}'), 3),
                                        (Event("[DONE]"), 4), (Event("late"), 5)])
        result = inspect("stream", wire, CONFIG)
        self.assertTrue({"stream_error_event", "stream_json", "stream_error_payload", "data_after_done"}.issubset(codes(result)))
        self.assertNotIn("SECRET", json.dumps(result.to_dict()))

    def test_findings_deduplicated_under_bad_stream(self):
        parts = [chunk({"content": []}) for _ in range(100)]
        result = self.result(parts)
        self.assertLess(len(result.findings), 10)


    def test_first_tool_delta_excludes_name_only_event(self):
        parts = [chunk({"role": "assistant"}),
                 chunk({"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                        "function": {"name": "handshake_echo", "arguments": ""}}]}),
                 chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"value":7}'}}]}),
                 chunk(finish="tool_calls")]
        result = self.result(parts, "tool-stream")
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.metrics["first_delta_ms"], 2.0)

    def test_usage_attached_to_content_is_not_terminal(self):
        parts = stream_chunks()
        parts[1]["usage"] = {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16}
        result = self.result(parts, "stream-usage")
        self.assertEqual(result.status, "warn")
        self.assertIn("usage_not_terminal", codes(result))

    def test_usage_before_finish_is_not_terminal(self):
        parts = stream_chunks()
        parts.insert(1, chunk(usage_only=True))
        self.assertIn("usage_not_terminal", codes(self.result(parts, "stream-usage")))
