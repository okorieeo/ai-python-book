python -m agent_kit.walkthrough

user: Rename my egg chat to Egg report, and delete my feed chat.

REQUEST 1 ended with status: needs_approval
  waiting for approval: delete_conversation {'conversation_id': 2}
  run state saved (1,483 bytes of JSON). Nothing has been deleted yet: conversation 2 exists = True

REQUEST 2: the user clicks Approve
  status: completed | conversation 2 exists = False | conversation 1 title = 'Egg report'

TRANSCRIPT
  user      Rename my egg chat to Egg report, and delete my feed chat.
  assistant tool_use    list_conversations {}  [toolu_1]
  user      tool_result [toolu_1] [{"id": 1, "title": "Egg production", "messages": 2}, {"i...
  assistant tool_use    rename_conversation {"conversation_id": 1, "new_title": "Egg report"}  [toolu_2]
  assistant tool_use    delete_conversation {"conversation_id": 2}  [toolu_3]
  user      tool_result [toolu_2] Conversation 1 is now titled 'Egg report'.
  user      tool_result [toolu_3] Conversation 2 was deleted.
  assistant text: All done. Your egg chat is now 'Egg report'. The feed chat was handled as you decided.

model calls: 3 | tool calls: 3 | tokens in=1790 out=145 | cost $0.005030
audit: list_conversations:ok, rename_conversation:ok, delete_conversation:pending, delete_conversation:ok
