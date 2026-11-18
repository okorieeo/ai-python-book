from django.db.models import Count, QuerySet

class ConversationQuerySet(QuerySet):
    def for_user(self, user):
        return self.filter(user=user)               # the ownership filter lives in ONE place

    def with_message_counts(self):
        return self.annotate(message_count=Count("messages"))

class Conversation(models.Model):
    ...
    objects = ConversationQuerySet.as_manager()

# usage: Conversation.objects.for_user(request.user).with_message_counts()[:20]
