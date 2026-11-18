from django.db.models import Count, F, Q, Sum

# OR conditions
Conversation.objects.filter(Q(title__icontains="docker") | Q(user__email__endswith="@example.com"))

# Compare or compute using columns, in the database
Message.objects.filter(output_tokens__gt=F("input_tokens"))

# Aggregates and annotations
UsageRecord.objects.filter(user=ada).aggregate(total=Sum(F("input_tokens") + F("output_tokens")))
Conversation.objects.annotate(message_count=Count("messages")).filter(message_count__gt=10)
