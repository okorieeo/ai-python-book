mkdir -p ~/projects/ai-chat-app/backend
cd ~/projects/ai-chat-app/backend
python3 -m venv .venv
source .venv/bin/activate

pip install "Django>=6.1,<6.2" "djangorestframework>=3.18,<3.19" \
            "djangorestframework-simplejwt>=5.5,<5.6" "google-auth>=2.40"
pip freeze > requirements.txt

django-admin startproject config .
python manage.py startapp accounts
