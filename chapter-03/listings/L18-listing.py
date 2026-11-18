import json

def parse_ai_json(text: str) -> dict:
    """Parse a model reply that should contain a JSON object."""
    cleaned = text.strip()
    if cleaned.startswith("```"):                      # strip markdown fences
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError(f"Model did not return valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data

reply = '{"sentiment": "positive", "score": 0.92}'
result = parse_ai_json(reply)
print(result.get("sentiment"))
