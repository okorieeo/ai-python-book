API=http://localhost:8000/api/v1
CONV=<a conversation id>   TOKEN=<your access token>

# AC-1: create a link (the url is in this response only)
curl -s -X POST $API/conversations/$CONV/share/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"expires_in": "1d"}'

# AC-3: read it with NO credentials, using the token from the url
curl -s -i $API/public/shared/<token from the url>/

# AC-6: a made-up token gets the same 404 as an expired or revoked one
curl -s -i $API/public/shared/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/
