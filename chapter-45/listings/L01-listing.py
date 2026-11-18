>>> kept, dropped = trim_history(five_messages_of_10_tokens, max_tokens=30)
>>> [m.content[0] for m in kept], dropped
(['c', 'd', 'e'], 2)

>>> send()                                   # the provider times out once
1st call: 503 the AI provider did not answer in time; retry with the same Idempotency-Key
>>> send()                                   # retry with the same key
retry: echo: hello deduplicated= False
>>> send()                                   # a double click, or a client retry
again: echo: hello deduplicated= True
provider calls: 2 | user messages stored: 1
>>> send(user_id="ada", conversation_id="c2")      # c2 belongs to bo
other user's conversation: 404 conversation not found
