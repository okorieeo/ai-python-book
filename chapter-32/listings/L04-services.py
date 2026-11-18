from attachments.content import UNTRUSTED_CONTENT_RULES, build_user_content
from attachments.services import attach_to_message

def send_user_message(*, user, conversation, content, client_id=None,
    attachment_ids=()):
    message, created = create_user_message(
        user=user, conversation=conversation, content=content, client_id=client_id
    )
    if not created:
        return message                      # a retry: do not call the model twice
    attachments = attach_to_message(user=user, message=message,
        public_ids=list(attachment_ids))
    blocks = build_user_content(content, attachments)      # pictures and PDFs
        first, the question last
    start_ai_reply(
        conversation,
        system=SYSTEM_PROMPT + "\n\n" + UNTRUSTED_CONTENT_RULES,
        user_content=blocks,                # your Chapter 29 function builds the
            API request
    )
    return message
