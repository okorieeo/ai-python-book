# Chapter 25 code: Mobile UX and Performance

## mobile/  (copy into your Expo app, e.g. ai-chat-app/mobile)
- `lib/`, `hooks/`, `components/`, `app/*.example.tsx`: see chapter sections 25.3 to 25.14.
- `__tests__/`: 93 tests. They need no phone or emulator.

    npm install --save-dev tsx @types/node
    npm test            # tsx --test __tests__/*.test.ts   (Node 22 or newer)
    npm run typecheck   # tsc --noEmit

Verified with: Expo SDK 58 (React Native 0.88.1, React 19.3.0), NetInfo 12.0.1, AsyncStorage 2.2.0,
TanStack Query 5.105, FlashList 2.3.2, TypeScript 7.0.2. Not run on a phone, emulator or simulator.

`*.example.tsx` files show how to merge the pieces into your own layout and screens (Chapters 23 and 24).

## backend/chat/  (merge into your Django chat app)
- `models_excerpt.py`: stand-in models; only `Message.client_id` and the unique constraint are new.
- `services.py`: ADD `create_user_message` and `ClientIdReused` to your services module.
- `serializers.py`, `views.py`, `urls.py`: the idempotent create endpoint.
- `test_idempotency.py`: 11 tests (adjust the URL and the user setup to your project).

    python manage.py makemigrations chat && python manage.py migrate
    python manage.py test chat.test_idempotency

Verified with Django 6.1.3, DRF 3.18.3 and SQLite in a minimal project.
