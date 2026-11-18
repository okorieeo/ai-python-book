"""Structured output: pull JSON out of model text, check it against a schema, retry once."""
import json
import re
from dataclasses import dataclass


class StructuredOutputError(ValueError):
    """The model's reply could not be turned into valid, schema-conforming data."""

    def __init__(self, message: str, problems: list = None):
        super().__init__(message)
        self.problems = problems or [message]


def extract_json(text: str):
    """Find the first JSON object or array in text. Tolerates prose and ``` fences around it."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char in "{[":
            try:
                value, _end = decoder.raw_decode(text, index)
            except json.JSONDecodeError:
                continue
            return value
    raise StructuredOutputError("No JSON found in the reply.")


_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _type_ok(value, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[expected])


def validate(value, schema: dict, path: str = "$") -> list:
    """Check value against a small JSON Schema subset. Returns a list of problems (empty = valid).

    Supports type, enum, required, properties, additionalProperties (false only),
    items, minLength, maxLength, minItems and maxItems. For bigger needs use the
    jsonschema package or a Pydantic model; this keeps the chapter dependency-free.
    """
    problems = []
    expected = schema.get("type")
    if expected and not _type_ok(value, expected):
        return [f"{path}: expected {expected}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            problems.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append(f"{path}: longer than {schema['maxLength']} characters")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            problems.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                problems.extend(validate(item, schema["items"], f"{path}[{i}]"))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"{path}: missing required field '{key}'")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    problems.append(f"{path}: unexpected field '{key}'")
        for key, sub_schema in properties.items():
            if key in value:
                problems.extend(validate(value[key], sub_schema, f"{path}.{key}"))
    return problems


def split_answer(text: str, tag: str = "answer"):
    """Split a "think first" reply into (scratchpad, answer).

    The answer is the text inside the LAST <answer>...</answer> block; the scratchpad is
    everything before it. Raises StructuredOutputError when there is no answer block, for
    example because the reply was cut off by max_tokens.
    """
    matches = list(re.finditer(rf"<{tag}>(.*?)</{tag}>", text, re.S))
    if not matches:
        raise StructuredOutputError(f"No <{tag}> block in the reply.")
    last = matches[-1]
    return text[: last.start()].strip(), last.group(1).strip()


def parse_structured(text: str, schema: dict):
    """extract_json + validate. Returns the data or raises StructuredOutputError."""
    data = extract_json(text)
    problems = validate(data, schema)
    if problems:
        raise StructuredOutputError("The JSON does not match the schema.", problems)
    return data


@dataclass
class StructuredResult:
    data: object
    attempts: int
    input_tokens: int
    output_tokens: int


def complete_structured(llm, *, system: str, messages: list, schema: dict,
                        max_tokens: int = 800, max_retries: int = 1) -> StructuredResult:
    """Call the model, parse and validate the reply, and retry with the error text if needed.

    The retry shows the model its own bad reply and the exact problems, then asks for a
    corrected reply. It does not use assistant "prefill", which the newest Claude
    models reject. Raises StructuredOutputError when every attempt fails.
    """
    conversation = list(messages)
    input_tokens = output_tokens = 0
    last_error = None
    for attempt in range(1, max_retries + 2):
        result = llm.complete(system=system, messages=conversation, max_tokens=max_tokens, schema=schema)
        input_tokens += result.input_tokens
        output_tokens += result.output_tokens
        try:
            data = parse_structured(result.text, schema)
            return StructuredResult(data, attempt, input_tokens, output_tokens)
        except StructuredOutputError as error:
            last_error = error
            conversation = list(messages) + [
                {"role": "assistant", "content": result.text},
                {"role": "user", "content": (
                    "Your previous reply was not valid. Problems: "
                    + "; ".join(prob.rstrip(".") for prob in error.problems)
                    + ". Reply again with only the corrected JSON.")},
            ]
    raise StructuredOutputError(
        f"No valid output after {max_retries + 1} attempts.", last_error.problems if last_error else None
    )
