"""Bug 3: customers get the receipt email twice. The task is retried after it already sent."""


def send_receipt(order_id, mailer, store):
    mailer.send(order_id)            # side effect happens first
    store.mark_sent(order_id)        # ...then this fails, and the whole task runs again
