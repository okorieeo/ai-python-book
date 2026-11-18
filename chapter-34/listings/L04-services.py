from chat import ai_pipeline

def send_message(*, user, conversation, text, safety, provider):
    history = [{"role": m.role, "content": m.content} for m in conversation.messages.order_by("created_at")]
    turn = ai_pipeline.prepare_turn(user=user, history=history, new_text=text, safety=safety)
    if turn.refusal:
        return {"content": turn.refusal, "blocked": True, "ai_generated": False}
    reply = provider.complete(turn.messages)                   # Chapter 29: timeouts, budgets, fallbacks
    result = ai_pipeline.finish_turn(turn=turn, reply=reply, safety=safety)
    return {**result, "ai_generated": True}
