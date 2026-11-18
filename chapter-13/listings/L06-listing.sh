curl -s -X POST localhost:8000/api/v1/auth/token/refresh \
     -H "Content-Type: application/json" -d "{\"refresh\": \"$REFRESH\"}"      # works

curl -s -X POST localhost:8000/api/v1/auth/token/refresh \
     -H "Content-Type: application/json" -d "{\"refresh\": \"$REFRESH\"}"      # old token
 example output
{"access":"eyJhbGciOiJIUzI1NiIsInR5...","refresh":"eyJhbGciOiJIUzI1NiIsInR5..."}

{"error":{"code":"not_authenticated","message":"The token is not valid.","request_id":"req_00a606"}}
