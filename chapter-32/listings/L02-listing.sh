cd ~/projects/ai-chat-app && git checkout main && git pull
git checkout -b feature/multimodal

# backend
cd backend && source .venv/bin/activate
pip install pillow pypdf openai celery
pip freeze | grep -i -E "^(pillow|pypdf|openai|celery)==" >> requirements.txt   #
    or your own way of pinning (Chapter 11)
ffmpeg -version | head -1        # install it first if this fails: sudo apt install
    ffmpeg  or  brew install ffmpeg

# mobile
cd ../mobile
npx expo install expo-audio expo-camera expo-image-picker expo-image-manipulator
npx expo install expo-speech expo-sensors expo-document-picker
npm install --save-dev tsx @types/node
