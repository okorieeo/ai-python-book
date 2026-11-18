cd ~/projects/ai-chat-app
git checkout main && git pull
git checkout -b feature/backend-security

cd backend && source .venv/bin/activate
echo "cryptography" >> requirements.txt
printf "pip-audit\nbandit\n" >> requirements-dev.txt
pip install -r requirements-dev.txt
pip freeze > requirements.lock.txt
