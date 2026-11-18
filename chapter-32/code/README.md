# Chapter 32 code: Multimodal and Specialized AI Features

## backend/attachments/  (a Django app for your chat project)
- `sniff.py`, `limits.py`, `vision_math.py`: file type from bytes, every limit in one place, image token cost.
- `images.py`, `documents.py`, `audio.py`: normalise pictures, inspect PDFs, convert audio with ffmpeg.
- `providers.py`, `speech_text.py`, `speech_service.py`: speech adapters (configuration, not code), dictation, read-aloud with a cache.
- `models.py`, `services.py`, `tasks.py`, `views.py`, `serializers.py`, `urls.py`: the attachment pipeline.
- `content.py`: model request blocks and the untrusted-content fence.
- `test_*.py`, `testing.py`, `tests_pdf.py`: 106 tests. They import `Conversation` and `Message` from `chat.models`:
  adjust `testing.py` to your own models. They need `ffmpeg` and `ffprobe` on the path.

    pip install pillow pypdf openai celery
    python manage.py makemigrations attachments && python manage.py migrate
    python manage.py test attachments

Verified with Django 6.1.3, DRF 3.18.3, Celery 5.7 (eager), Pillow 13, pypdf 6.21, ffmpeg 6.1, openai 3.46,
anthropic 2.6 (SDK 2 uses httpx2 for its mock transport).

## mobile/  (copy into your Expo app)
- `lib/media`, `lib/cv`, `hooks`, `components`: sections 32.11 to 32.15.
- `lib/net/*` and `lib/api/client.ts` are the Chapter 25 files. The only change is the new `getApiConfig()` export in `client.ts`.
- `__tests__/`: 63 tests, no phone needed.

    npm install --save-dev tsx @types/node
    npm test           # tsx --test __tests__/*.test.ts   (Node 22 or newer)
    npm run typecheck  # tsc --noEmit

Verified with Expo SDK 58 (React Native 0.88.1), expo-audio, expo-camera, expo-image-picker, expo-image-manipulator,
expo-speech, expo-sensors, expo-document-picker, TypeScript 7.0.2. Not run on a phone, emulator or simulator.
After adding the `app.json` plugins from section 32.11, make a new development build (Chapter 26).
