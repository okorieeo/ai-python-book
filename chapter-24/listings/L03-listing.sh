cd ~/projects/ai-chat-app/backend
source .venv/bin/activate
python manage.py makemigrations devices
python manage.py migrate
python manage.py test devices documents
 example output
Found 40 test(s).
Creating test database for alias 'default'...
........................................
----------------------------------------------------------------------
Ran 40 tests in 14.2s
OK
Destroying test database for alias 'default'...
