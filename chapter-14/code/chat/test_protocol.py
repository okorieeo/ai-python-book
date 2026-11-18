import json
import unittest

from .protocol import MAX_CONTENT_CHARS, ProtocolError, error_message, parse_client_message, server_message

def frame(**payload) -> str:
    return json.dumps(payload)

class ParseClientMessageTests(unittest.TestCase):
    def test_valid_message_send_is_parsed_and_trimmed(self):
        env = parse_client_message(frame(type="message.send", id="c-1",
                                         data={"conversation_id": "abc", "content": "  hello  "}))
        self.assertEqual(env.type, "message.send")
        self.assertEqual(env.id, "c-1")
        self.assertEqual(env.data, {"conversation_id": "abc", "content": "hello"})

    def test_ping_needs_no_data(self):
        self.assertEqual(parse_client_message(frame(type="ping")).type, "ping")

    def test_invalid_json(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_client_message("{not json")
        self.assertEqual(ctx.exception.code, "invalid_json")

    def test_json_must_be_an_object(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_client_message("[1, 2, 3]")
        self.assertEqual(ctx.exception.code, "invalid_json")

    def test_unknown_type_keeps_the_client_ref(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_client_message(frame(type="hack.server", id="x-9"))
        self.assertEqual((ctx.exception.code, ctx.exception.ref), ("unknown_type", "x-9"))

    def test_blank_content_reports_the_field(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_client_message(frame(type="message.send", id="c-2", data={"conversation_id": "abc", "content": "   "}))
        self.assertEqual(ctx.exception.code, "validation_error")
        self.assertIn("content", ctx.exception.details)
        self.assertEqual(ctx.exception.ref, "c-2")

    def test_content_too_long(self):
        data = {"conversation_id": "abc", "content": "x" * (MAX_CONTENT_CHARS + 1)}
        with self.assertRaises(ProtocolError) as ctx:
            parse_client_message(frame(type="message.send", data=data))
        self.assertIn("content", ctx.exception.details)

    def test_oversized_frame_is_rejected_before_parsing(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_client_message("x" * 20_000)
        self.assertEqual(ctx.exception.code, "message_too_large")

    def test_cancel_requires_generation_id(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_client_message(frame(type="generation.cancel", data={}))
        self.assertIn("generation_id", ctx.exception.details)

    def test_bad_client_id_is_rejected(self):
        with self.assertRaises(ProtocolError) as ctx:
            parse_client_message(frame(type="ping", id="has spaces!"))
        self.assertEqual(ctx.exception.code, "validation_error")

    def test_data_must_be_an_object(self):
        with self.assertRaises(ProtocolError):
            parse_client_message(frame(type="ping", data="oops"))

class ServerMessageTests(unittest.TestCase):
    def test_error_message_shape(self):
        error = ProtocolError("validation_error", "The message data is invalid.", "c-2", {"content": ["blank"]})
        self.assertEqual(error_message(error), {
            "type": "error", "ref": "c-2",
            "data": {"code": "validation_error", "message": "The message data is invalid.",
                     "details": {"content": ["blank"]}},
        })

    def test_server_message_without_ref(self):
        self.assertEqual(server_message("pong"), {"type": "pong", "data": {}})

if __name__ == "__main__":
    unittest.main()
