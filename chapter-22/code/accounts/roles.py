"""Who may do what. The API enforces this; the UI only mirrors it."""

ALL_PERMISSIONS = ["view_users", "export_users", "view_analytics"]

PERMISSIONS_BY_ROLE = {
    "member": [],
    "support": ["view_users"],                  # read-only access to accounts
    "admin": ["view_users", "export_users", "view_analytics"],
}

def permissions_for(user):
    if not user.is_authenticated:
        return []
    if user.is_superuser:
        return list(ALL_PERMISSIONS)
    return list(PERMISSIONS_BY_ROLE.get(user.role, []))
