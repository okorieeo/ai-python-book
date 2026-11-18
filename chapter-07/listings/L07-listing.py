# BAD: 1 query for conversations + 1 query per conversation to get the user = N+1
for conv in Conversation.objects.all()[:50]:
    print(conv.title, conv.user.email)

# GOOD: fetch related rows in the same query (one-to-one / foreign key) ...
for conv in Conversation.objects.select_related("user")[:50]:
    print(conv.title, conv.user.email)

# ... or in one extra query for reverse/many relations
convs = Conversation.objects.prefetch_related("messages")[:50]
