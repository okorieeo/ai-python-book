curl https://api.anthropic.com/v1/messages \
  -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-sonnet-5-5",
    "max_tokens": 1024,
    "system": "You are a concise assistant for a poultry farm app.",
    "messages": [
      {"role": "user", "content": "In one sentence, what is a token?"}
    ]
  }'
