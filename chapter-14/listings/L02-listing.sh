python simulate_chat.py 0.3

-> {"type": "message.send", ...}
<- {"type": "message.accepted", ...}
<- {"type": "assistant.delta", "data": {..., "text": "You "}}
<- {"type": "assistant.delta", "data": {..., "text": "said: "}}
<- {"type": "assistant.delta", "data": {..., "text": "Explain "}}
-> generation.cancel
   [saved as canceled: 'You said: Explain ', usage=Usage(input_tokens=4, output_tokens=4)]
<- {"type": "assistant.end", "data": {..., "message_id": "msg_2", "status": "canceled", "usage": {"input_tokens": 4, "output_tokens": 4}}}
