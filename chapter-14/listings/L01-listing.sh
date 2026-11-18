python simulate_chat.py

-> {"type": "message.send", "id": "c-1", "data": {"conversation_id": "conv-1", "content": "Explain WebSockets"}}
<- {"type": "message.accepted", "data": {"message_id": "msg_1", "generation_id": "gen_33445f17b2"}, "ref": "c-1"}
<- {"type": "assistant.delta", "data": {"generation_id": "gen_33445f17b2", "text": "You "}}
<- {"type": "assistant.delta", "data": {"generation_id": "gen_33445f17b2", "text": "said: "}}
<- {"type": "assistant.delta", "data": {"generation_id": "gen_33445f17b2", "text": "Explain "}}
   ... one delta per word ...
   [saved as completed: 'You said: Explain WebSockets. This is a simulated streaming answer, ...']
<- {"type": "assistant.end", "data": {"generation_id": "gen_fde4a3d3b1", "message_id": "msg_2", "status": "completed", "usage": {"input_tokens": 4, "output_tokens": 47}}}
