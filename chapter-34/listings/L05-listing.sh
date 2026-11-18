# 1) what must this user accept?
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/privacy/consent/
# expected shape: {"must_accept": ["privacy_notice", "terms"], "choices": {}}

# 2) grant an optional purpose, then read it back
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"purpose": "improvement", "granted": true}' http://localhost:8000/api/v1/privacy/consent/

# 3) download my data (needs the password; rate limited to 3 an hour)
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"password": "your-password"}' -o my-data.zip http://localhost:8000/api/v1/privacy/export/
unzip -l my-data.zip       # README.txt, data.json, conversations/<id>.txt

# 4) schedule deletion (reversible for 14 days)
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"password": "your-password", "confirm": "DELETE"}' http://localhost:8000/api/v1/privacy/delete/
