LOGIN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "ada@example.com", "password": "correct-horse-battery-staple"}')
ACCESS=$(echo $LOGIN | python3 -c "import sys,json; print(json.load(sys.stdin)['access'])")
REFRESH=$(echo $LOGIN | python3 -c "import sys,json; print(json.load(sys.stdin)['refresh'])")

curl -s localhost:8000/api/v1/me -H "Authorization: Bearer $ACCESS"
curl -s -i localhost:8000/api/v1/me                          # no token
 example output
{"id":"b473b324-b757-4636-9322-7ed706399ed0","email":"ada@example.com","name":"Ada",
 "role":"member","email_verified":true,"created_at":"2026-11-02T04:17:57.540095Z"}

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
{"error":{"code":"not_authenticated","message":"Missing or invalid credentials.","request_id":"req_13de7d"}}
