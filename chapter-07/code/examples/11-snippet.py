from django.db import transaction

def save_assistant_reply(conversation, text, input_tokens, output_tokens, model_name):
    with transaction.atomic():
        message = Message.objects.create(
            conversation=conversation, role="assistant", content=text,
            input_tokens=input_tokens, output_tokens=output_tokens, model_name=model_name,
        )
        UsageRecord.objects.create(
            user=conversation.user, message=message,
            input_tokens=input_tokens, output_tokens=output_tokens,
        )
        conversation.save(update_fields=["updated_at"])      # bump "last activity"
    return message
