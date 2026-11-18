qs = Conversation.objects.filter(user=ada)      # no query yet
qs = qs.order_by("-updated_at")                # still no query
first_page = list(qs[:20])                      # NOW one query with LIMIT 20
count = qs.count()                              # a separate COUNT(*) query
