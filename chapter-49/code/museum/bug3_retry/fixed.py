"""Make the task safe to run twice (idempotent): check first, and give the provider a stable key."""


def send_receipt(order_id, mailer, store):
    if store.is_sent(order_id):
        return "already sent"
    mailer.send(order_id, idempotency_key=f"receipt-{order_id}")
    store.mark_sent(order_id)
    return "sent"
