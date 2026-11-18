"""The WebSocket message protocol from Chapter 8, as plain Python (no Django, no Channels)."""
import json
import re
from dataclasses import dataclass, field
from typing import Any

MAX_FRAME_BYTES = 16_384          # reject huge frames before parsing them
MAX_CONTENT_CHARS = 8_000
CLIENT_TYPES = {"message.send", "generation.cancel", "ping"}
VALID_CLIENT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

class ProtocolError(Exception):
    """A problem with a client message. Becomes an `error` message, never a crash."""

    def __init__(self, code: str, message: str, ref: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.ref = ref
        self.details = details or {}

@dataclass(frozen=True)
class Envelope:
    type: str
    id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

def _field_error(ref, **fields: str) -> ProtocolError:
    return ProtocolError("validation_error", "The message data is invalid.", ref,
                         {name: [problem] for name, problem in fields.items()})

def parse_client_message(raw: str | bytes) -> Envelope:
    """Turn one incoming frame into a validated Envelope, or raise ProtocolError."""
    size = len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)
    if size > MAX_FRAME_BYTES:
        raise ProtocolError("message_too_large", f"Messages may not exceed {MAX_FRAME_BYTES} bytes.")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ProtocolError("invalid_json", "The message is not valid JSON.") from None
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_json", "The message must be a JSON object.")

    ref = payload.get("id")
    if ref is not None and not (isinstance(ref, str) and VALID_CLIENT_ID.match(ref)):
        raise ProtocolError("validation_error", "The message id is invalid.", None, {"id": ["Use 1 to 64 letters, digits or . _ : -"]})

    message_type = payload.get("type")
    if message_type not in CLIENT_TYPES:
        raise ProtocolError("unknown_type", "Unknown message type.", ref)

    data = payload.get("data", {})
    if not isinstance(data, dict):
        raise _field_error(ref, data="Must be an object.")

    if message_type == "message.send":
        conversation_id = data.get("conversation_id")
        content = data.get("content")
        if not isinstance(conversation_id, str) or not 0 < len(conversation_id) <= 64:
            raise _field_error(ref, conversation_id="This field is required.")
        if not isinstance(content, str) or not content.strip():
            raise _field_error(ref, content="This field may not be blank.")
        if len(content) > MAX_CONTENT_CHARS:
            raise _field_error(ref, content=f"Ensure this field has no more than {MAX_CONTENT_CHARS} characters.")
        data = {"conversation_id": conversation_id, "content": content.strip()}
    elif message_type == "generation.cancel":
        generation_id = data.get("generation_id")
        if not isinstance(generation_id, str) or not generation_id:
            raise _field_error(ref, generation_id="This field is required.")
        data = {"generation_id": generation_id}
    else:
        data = {}
    return Envelope(type=message_type, id=ref, data=data)

def server_message(type_: str, data: dict | None = None, ref: str | None = None) -> dict:
    message: dict[str, Any] = {"type": type_, "data": data or {}}
    if ref is not None:
        message["ref"] = ref
    return message

def error_message(error: ProtocolError) -> dict:
    data: dict[str, Any] = {"code": error.code, "message": error.message}
    if error.details:
        data["details"] = error.details
    return server_message("error", data, error.ref)
