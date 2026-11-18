import pytest

from agent_kit.demo_app import build_registry
from agent_kit.tools import Tool, ToolRegistry

OK_SCHEMA = {"type": "object", "properties": {"x": {"type": "integer"}}, "additionalProperties": False}
DESC = "Does something useful and explains when to use it, and what it returns."


def make(**kw):
    base = dict(name="t", description=DESC, input_schema=OK_SCHEMA, handler=lambda a, c: "ok")
    base.update(kw)
    return Tool(**base)


def test_valid_tool_builds_a_definition():
    d = make(name="get_thing").definition()
    assert d["name"] == "get_thing" and d["input_schema"] == OK_SCHEMA and "strict" not in d


def test_strict_tools_add_the_flag_and_need_additional_properties_false():
    assert make(strict=True).definition()["strict"] is True
    with pytest.raises(ValueError, match="additionalProperties"):
        make(strict=True, input_schema={"type": "object", "properties": {}})


@pytest.mark.parametrize("bad", ["has space", "", "x" * 65, "dot.name"])
def test_bad_names_are_rejected(bad):
    with pytest.raises(ValueError, match="Tool name"):
        make(name=bad)


def test_short_descriptions_bad_risk_and_bad_schema_are_rejected():
    with pytest.raises(ValueError, match="description"):
        make(description="too short")
    with pytest.raises(ValueError, match="risk"):
        make(risk="dangerous")
    with pytest.raises(ValueError, match="object"):
        make(input_schema={"type": "string"})
    with pytest.raises(Exception):
        make(input_schema={"type": "object", "properties": {"x": {"type": "nonsense"}}})


def test_validation_messages_are_readable():
    t = build_registry().get("rename_conversation")
    assert t.validate({"conversation_id": 1, "new_title": "ok"}) == []
    assert any("new_title" in p for p in t.validate({"conversation_id": 1, "new_title": ""}))
    assert any("conversation_id" in p for p in t.validate({"conversation_id": "one", "new_title": "x"}))
    assert any("required" in p for p in t.validate({"new_title": "x"}))
    assert any("additional" in p.lower() for p in t.validate({"conversation_id": 1, "new_title": "x", "sudo": True}))
    assert t.validate("not an object") == ["the input must be a JSON object"]


def test_registry_rejects_duplicates_and_can_hide_tools():
    reg = build_registry()
    with pytest.raises(ValueError, match="already registered"):
        reg.register(reg.get("list_conversations"))
    names = [d["name"] for d in reg.definitions(allowed={"list_conversations"})]
    assert names == ["list_conversations"]
    assert ToolRegistry().definitions() == []
