from agent_kit.demo_app import build_registry
print(json.dumps(build_registry().get("rename_conversation").definition(), indent=2))

{
  "name": "rename_conversation",
  "description": "Changes the title of one of the current user's conversations. Use it only when the user clearly asks for a rename, and get the conversation id from list_conversations first. The change is easy to undo, so it does not need approval.",
  "input_schema": {
    "type": "object",
    "properties": {
      "conversation_id": {
        "type": "integer",
        "description": "The conversation's id."
      },
      "new_title": {
        "type": "string",
        "minLength": 1,
        "maxLength": 80,
        "description": "The new title, 80 characters at most."
      }
    },
    "required": [
      "conversation_id",
      "new_title"
    ],
    "additionalProperties": false
  }
}
