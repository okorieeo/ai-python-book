docker run -d --name backend --network appnet \
  --env-file ../.env.docker \
  -e DJANGO_SECRET_KEY_FILE=/run/secrets/django_secret_key \
  -v "$PWD/../secrets/django_secret_key:/run/secrets/django_secret_key:ro" \
  -e WAIT_FOR="db:5432 redis:6379" -e RUN_MIGRATIONS=true \
  -p 127.0.0.1:8000:8000 \
  ai-chat-backend:dev
 
docker logs -f backend
