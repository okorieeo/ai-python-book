cd ~/projects/ai-chat-app/backend
source .venv/bin/activate
pip install "django-storages[s3]" Pillow requests "moto[s3]"
pip freeze > requirements.txt

python manage.py startapp documents
python manage.py startapp notifications
# add "documents" and "notifications" to INSTALLED_APPS, copy the files from this chapter

python manage.py makemigrations accounts documents notifications
python manage.py migrate
python manage.py test accounts documents notifications
 expected output
Found 65 test(s).
Creating test database for alias 'default'...
.................................................................
----------------------------------------------------------------------
Ran 65 tests in 31.101s
OK
Destroying test database for alias 'default'...
