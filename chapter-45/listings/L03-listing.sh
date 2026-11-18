# two users: Ada creates a conversation; Bo must not be able to read, send to or delete it
curl -s -H "Authorization: Bearer $BO_TOKEN" http://localhost:8000/api/v1/conversations/$ADA_CONV/          # expected: 404
curl -s -X POST -H "Authorization: Bearer $BO_TOKEN" -H "Idempotency-Key: abcdefgh" -H "Content-Type: application/json" \
     -d '{"content":"hi"}' http://localhost:8000/api/v1/conversations/$ADA_CONV/send/                         # expected: 404

# the same key twice: one message
for i in 1 2; do curl -s -X POST -H "Authorization: Bearer $ADA_TOKEN" -H "Idempotency-Key: abcdefgh" \
     -H "Content-Type: application/json" -d '{"content":"hi"}' http://localhost:8000/api/v1/conversations/$ADA_CONV/send/ ; echo; done
# expected: 201 then 200, the same reply both times; the database holds one user message
