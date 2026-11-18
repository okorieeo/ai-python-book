# Add these two members to the Action enum in audit/services.py (Chapter 17):
#
#     SHARE_LINK_CREATED = "share.link_created"
#     SHARE_LINK_REVOKED = "share.link_revoked"
#
# And in config/settings.py:
#
#     INSTALLED_APPS += ["sharing"]
#     SHARE_PUBLIC_BASE_URL = env("SHARE_PUBLIC_BASE_URL", default="http://localhost:3000")
