# Create the first admin user
docker compose exec backend python manage.py createsuperuser
 
# A Django shell, and a SQL shell
docker compose exec backend python manage.py shell
docker compose exec db psql -U chat chat
 
# A database backup. -T turns off the terminal so the dump is not corrupted
docker compose exec -T db pg_dump -U chat chat > backup.sql
 
# Restore into an EMPTY database (a fresh project or fresh volume)
docker compose exec -T db psql -U chat chat < backup.sql
