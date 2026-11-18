B=localhost:8000/api/v1
TOKEN=...an access token from POST $B/auth/login...

for f in report.pdf flaky.pdf corrupt.pdf; do
  curl -s -X POST $B/documents -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' -d "{\"filename\":\"$f\"}" \
    -o /dev/null -w "POST $f -> %{http_code}\n"
done
curl -s "$B/documents?ordering=filename" -H "Authorization: Bearer $TOKEN"
