# Chapter 8 — API Design: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## REST Principles › What happens to a request

*(figure: see the printed book)*

Every endpoint you design follows these same five steps. When we build in Django, each step maps to a concrete piece of Django REST Framework: authentication classes, permission classes, serializers, service functions and models.


## Designing for AI Features › Pattern 4: rate limits and plan limits

Every AI call costs real money, so limiting is a financial control as much as a security one. There are two different limits, and they need two different error codes:

- `rate_limited` means "you are calling too fast" (for example 60 requests per minute). It is temporary; the client waits and retries.
- `plan_limit_reached` means "you have used your plan’s quota" (the `monthly_token_limit` of Chapter 7). Retrying is pointless; the app should show an upgrade screen.
Both use `429 Too Many Requests`, and both should tell the client what to do next:

**http**

```
HTTP/1.1 429 Too Many Requests
Retry-After: 30
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
```

> **Check the limit before you pay for the model call**
>
> Read the user’s usage from the ledger and compare it with the plan **before** calling the model provider, not afterwards. Rejecting a request is free; answering it and then discovering the user was over quota is not.


## Authentication Patterns › Pattern C: OAuth 2.0 and social login

**OAuth 2.0** lets users sign in through a provider they already trust, such as Google or Apple, without giving your app a password. The flow in plain words:

1. Your app sends the user to the provider’s sign-in page.
2. The user approves, and the provider redirects back to your app with a short-lived **authorization code**.
3. Your backend exchanges that code with the provider for proof of the user’s identity (their verified email and a stable id).
4. Your backend finds or creates the matching user in **your own**  `users` table, then issues **your own** access and refresh tokens.
Step 4 matters. Even with social login, your API keeps using its own tokens. OAuth is a way to *sign in*; it does not replace your session or JWT layer. That also means the rest of your API does not care how the user signed in.
