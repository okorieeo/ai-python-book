# log in and keep the cookies
curl -s -c jar.txt -X POST localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ada@example.com","password":"correct-horse-battery"}'

# a normal write works
curl -s -b jar.txt -X POST localhost:3000/api/v1/conversations \
  -H "Content-Type: application/json" -d '{"title":"From curl"}'

# the same write pretending to come from another website is refused
curl -s -b jar.txt -X POST localhost:3000/api/v1/conversations \
  -H "Content-Type: application/json" -H "Origin: https://evil.example" -d '{"title":"Attack"}'
# -> {"error":{"code":"csrf_blocked", ...}}
