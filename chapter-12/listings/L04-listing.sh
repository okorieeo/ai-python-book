B=localhost:8000/api/v1

# 1. log in and keep the access token
curl -s -X POST $B/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"ada","password":"pw-ada-1"}'
TOKEN=...paste the access value here...

# 2. create a conversation
curl -i -X POST $B/conversations -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"title":"Trip plan"}'

# 3. send a message twice with the same Idempotency-Key
curl -i -X POST $B/conversations/<id>/messages -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: abc-123' \
  -d '{"content":"Plan my trip"}'

# 4. break the rules and read the errors
curl -i $B/conversations                                   # no token
curl -s -X POST $B/conversations -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"title":""}'    # invalid
