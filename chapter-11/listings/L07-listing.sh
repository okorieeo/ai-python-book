ruff check . --fix
ruff format .
python manage.py test

cd ..
git checkout -b feature/backend-skeleton
git add backend .gitignore .env.example
git commit -m "feat: add Django project skeleton with custom user, chat models, health check and tests"
git push -u origin feature/backend-skeleton
