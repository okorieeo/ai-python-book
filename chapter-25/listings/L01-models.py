class Message(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE,
        related_name="messages")
    role = models.CharField(max_length=20)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    # NEW in Chapter 25: the key the phone generates once per message and repeats
        on every retry.
    client_id = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            # One message per (conversation, client_id). Rows with client_id NULL
                (the web client) never clash:
            # SQL treats NULLs as different values in a unique constraint.
            models.UniqueConstraint(fields=["conversation", "client_id"],
                name="uniq_message_client_id_per_conversation"),
        ]
