# DANGEROUS: if anything goes wrong in the check, the answer is "yes"
def can_view(user, conversation):
    try:
        return conversation.user_id == user.id or user.has_perm("chat.view_all")
    except Exception:
        return True

# SAFE: decide explicitly, catch only what you expect, and default to "no"
def can_view(user, conversation):
    if not user.is_authenticated:
        return False
    return conversation.user_id == user.id or user.has_perm("chat.view_all")
