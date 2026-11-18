Conversation.objects.filter(title__icontains="django")        # case-insensitive contains
Message.objects.filter(created_at__gte=start, created_at__lt=end)   # range
Conversation.objects.filter(user__email="ada@example.com")   # follow the foreign key
Message.objects.filter(role__in=["user", "assistant"])
Message.objects.filter(input_tokens__isnull=False)
UsageRecord.objects.filter(user=ada).order_by("-created_at")[:10]    # LIMIT 10
