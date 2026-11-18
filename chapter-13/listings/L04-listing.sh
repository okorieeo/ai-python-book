curl -s -X POST localhost:8000/api/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email": "bo@example.com", "name": "Bo", "password": "12345678"}'

curl -s -X POST localhost:8000/api/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email": "ada@example.com", "name": "Ada", "password": "correct-horse-battery-staple"}'
 example output
{"error":{"code":"validation_error","message":"The request contains invalid fields.",
 "request_id":"req_1b24f6","details":{"password":["This password is too common.",
 "This password is entirely numeric."]}}}

{"id":"b473b324-b757-4636-9322-7ed706399ed0","email":"ada@example.com","name":"Ada",
 "role":"member","email_verified":false,"created_at":"2026-11-02T04:17:57.540095Z"}
