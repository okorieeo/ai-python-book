curl -s -X POST localhost:8000/api/v1/farms -H "Authorization: Bearer $ACCESS" \
     -H "Content-Type: application/json" -d '{"name": "Green Acres"}'

curl -s -i localhost:8000/api/v1/admin/users -H "Authorization: Bearer $ACCESS"
 example output
{"id":"acea6876-ab1a-4550-b97a-4c4a326ebc13","name":"Green Acres","created_at":"2026-11-02T04:18:20.442076Z"}

HTTP/1.1 403 Forbidden
{"error":{"code":"permission_denied","message":"You do not have permission.","request_id":"req_27911f"}}
