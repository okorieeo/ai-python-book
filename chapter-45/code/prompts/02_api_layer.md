Using @docs/features/send-message.md and the models in @backend/conversations/models.py, plan then build the API layer.

Follow @CLAUDE.md: thin views, logic in services.py, reads in selectors.py (every selector takes the user).
Requirements:
- DRF ViewSet with explicit `permission_classes` and a `required_actions` map for the roles in @core/rbac.py (deny by default).
- Serializers list fields explicitly, mark server-controlled fields read-only, never expose integer ids or the user.
- Pagination on every list; throttle scope on the send action; `Idempotency-Key` header required.
- OpenAPI: `@extend_schema` on non-obvious actions so `python manage.py spectacular --validate` passes.
- Another user's object returns 404, not 403.

Write the failing tests for the acceptance criteria FIRST, run them, show me they fail, then implement until they pass.
Do not edit a test to make it pass without telling me why.
