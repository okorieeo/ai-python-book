conversation = {
    "id": 42,
    "messages": [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi! How can I help?"},
    ],
}

first = conversation["messages"][0]["content"]
print(first)                          # Hello

for msg in conversation["messages"]:
    print(f"{msg['role']}: {msg['content']}")
