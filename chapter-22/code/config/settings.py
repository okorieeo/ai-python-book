SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,           # otherwise "last login" stays empty
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AI Chat API",
    "DESCRIPTION": "REST API for the AI Chat SaaS (all paths under /api/v1).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {                 # two models both have a "role"
        "UserRoleEnum": "accounts.models.User.Role",
        "MessageRoleEnum": "chat.models.Message.Role",
    },
}
