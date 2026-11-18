cd ~/projects/ai-chat-app
git checkout main && git pull
git checkout -b feature/share-contract

# copy from the chapter download (keep the folder structure)
cp -r chapter_48_code/tools chapter_48_code/.claude .
cp chapter_48_code/CLAUDE.md CLAUDE.md      # or merge it into the one you already have
mkdir -p contracts docs/specs

python -m unittest discover -s tools/tests -t .
