# ADR-001: Use a modular monolith

Status: Accepted      Date: 2026-11-01

## Context
We are a small team building an AI chat product with web and mobile clients.
We need to ship an MVP quickly. Expected load is a few thousand daily users.

## Decision
Build one Django project split into modules (accounts, billing, chat, ai).
Deploy it as three containers from one image: web (ASGI), worker, scheduler.

## Alternatives considered
- Microservices: more flexible scaling, but far more operational complexity.
- Serverless functions: pay-per-use, but awkward for long-lived WebSockets.

## Consequences
+ Fast development, simple debugging, real database transactions.
+ Boundaries between modules keep a future split possible.
- The whole app scales together; a heavy module could force a split later.
