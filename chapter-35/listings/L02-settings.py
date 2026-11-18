INSTALLED_APPS += ["billing"]

BILLING_DEFAULT_CURRENCY = "USD"
BILLING_FREE_PLAN_CODE = "free"
BILLING_PAST_DUE_GRACE_DAYS = 7
BILLING_RENEWAL_GRACE_DAYS = 3
BILLING_MODEL_STANDARD = "claude-haiku-5-5"      # model ids stay in settings (Chapter 27)
BILLING_MODEL_PREMIUM = "claude-sonnet-5-5"

REST_FRAMEWORK["EXCEPTION_HANDLER"] = "billing.permissions.billing_exception_handler"
