curl https://jsonplaceholder.typicode.com/todos/1                # GET
curl -i https://jsonplaceholder.typicode.com/todos/1             # -i shows status + headers
curl -v https://jsonplaceholder.typicode.com/todos/1             # -v shows the whole conversation

curl -X POST https://jsonplaceholder.typicode.com/todos \
  -H "Content-Type: application/json" \
  -d '{"title": "Learn HTTP", "completed": false, "userId": 1}'

curl -H "Authorization: Bearer YOUR_TOKEN" https://api.example.com/me/
