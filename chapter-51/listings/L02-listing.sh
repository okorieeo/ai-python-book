python3 -c "import secrets; print(secrets.token_urlsafe(50))" > secrets/django_secret_key
chmod 644 secrets/django_secret_key
 
cat > .env.docker <<'END'
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
REDIS_URL=redis://redis:6379/0
END
DB_PASSWORD="$(cat secrets/db_password)"
printf "DATABASE_URL=postgres://chat:%s@db:5432/chat\n" "$DB_PASSWORD" >> .env.docker
git status --short
