ID=$(curl -s -X POST localhost:3100/api/conversations -H "Content-Type: application/json" \
     -d '{"title": "Demo"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

curl -s -X POST localhost:3100/api/conversations/$ID/messages \
     -H "Content-Type: application/json" -d '{"content": "Hello"}'

curl -s -X POST localhost:3100/api/conversations/$ID/messages \
     -H "Content-Type: application/json" -d '{"content": ""}'
 example output
{"userMessage":{"id":100,"role":"user","content":"Hello","createdAt":"2026-11-03T01:07:21.275Z"},
 "assistantMessage":{"id":101,"role":"assistant","content":"Echo: Hello","createdAt":"2026-11-03T01:07:21.275Z"}}

{"error":{"code":"validation_error","message":"The request contains invalid fields.",
 "request_id":"req_fdc4c6","details":{"content":["Enter 1 to 8000 characters."]}}}
