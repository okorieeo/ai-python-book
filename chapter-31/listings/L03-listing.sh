cd ~/projects/ai-chat-app
git checkout main && git pull
git checkout -b feature/knowledge-base

cd backend && source .venv/bin/activate
ls prompts prompt_library        # from Chapter 28: both must exist

unzip ~/Downloads/Chapter_31_code.zip -d /tmp/ch31
cp -r /tmp/ch31/chapter_31_code/rag /tmp/ch31/chapter_31_code/knowledge .
