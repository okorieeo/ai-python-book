curl -s -X POST localhost:8000/api/v1/conversations \
     -H "Authorization: Bearer demo-token" -d '{"title": "Invoices"}'

# copy the "id" from the response, then:
CID=<paste-the-id-here>

curl -s -X POST localhost:8000/api/v1/conversations/$CID/messages \
     -H "Authorization: Bearer demo-token" -d '{"content": "Hello"}'

curl -s "localhost:8000/api/v1/conversations/$CID/messages?limit=1" \
     -H "Authorization: Bearer demo-token"

curl -s -X POST localhost:8000/api/v1/conversations/$CID/messages \
     -H "Authorization: Bearer demo-token" -d '{"content": ""}'

curl -s localhost:8000/api/v1/conversations          # no token
