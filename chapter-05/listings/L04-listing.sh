curl -i http://localhost:8000/tasks
curl -i http://localhost:8000/tasks/1
curl -i http://localhost:8000/tasks/99                    # 404

curl -i -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Understand CORS"}'                       # 201

curl -i -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" -d '{"title": ""}'  # 400

curl -i -X DELETE http://localhost:8000/tasks/2            # 204
