python -m ai_lab.lab chatcost --turns 30 --user 100 --reply 300

A 30-turn chat: 800 system tokens, 100 tokens per question, 300 per reply. Every turn resends the history.
input tokens sent in total: 201,000 (vs 3,000 typed)
model                  total USD    USD / 1000 chats
claude-fable-5-1          2.4600             2460.00
claude-opus-5-5           0.9840              984.00
claude-sonnet-5-5         0.4920              492.00
claude-haiku-5-5          0.0246               24.60
