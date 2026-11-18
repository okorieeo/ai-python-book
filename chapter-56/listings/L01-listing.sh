ai-chat-saas/
  backend/
    config/        settings.py, asgi.py (HTTP + WebSocket routing), celery.py, urls.py
    accounts/      custom User, register / login / ws-ticket
    chat/          models, services, consumers, usage, tasks, REST views
    billing/       Plan, Subscription, WebhookEvent, gateways/, services, views
    ai/            providers.py (fake + Anthropic), memory.py, prompts.py
  clients/
    shared/        chat-protocol.ts, chat-state.ts, chat-client.ts, use-chat.ts
    web/           ChatPane.tsx, BillingPage.tsx
    mobile/        ChatScreen.tsx
