cd ~/projects/ai-chat-app && git checkout main && git pull
git checkout -b feature/quality-gates

# backend: the pinned tools
cd backend && source .venv/bin/activate
python -m pip install -r requirements-dev.txt

# mobile and web: the Prettier and ESLint packages from the package.scripts.json
    files
cd ../mobile && npm install --save-dev eslint@^9 eslint-config-expo prettier
    typescript@~6.0
cd ../web && npm install --save-dev eslint eslint-config-next prettier
    typescript@~6.0
