async def receive_json(self, content):
    service = get_chat_service()
    try:
        async for event in service.stream_reply(
            user_id=self.scope["user"].pk,
            conversation_id=self.conversation_id,
            text=content.get("text", ""),
        ):
            await self.send_json(event_to_dict(event))   # same events, different wire
    except (AIError, ConversationNotFound) as exc:
        await self.send_json({"type": "error", "code": getattr(exc, "code", "not_found")})
