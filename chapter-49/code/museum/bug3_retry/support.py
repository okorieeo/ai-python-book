"""Fakes for the retry demo: a mail service that records deliveries, a store that fails once,
and a tiny runner that retries on TransientError the way Celery's autoretry does."""


class TransientError(Exception):
    pass


class FakeMailer:
    def __init__(self):
        self.deliveries = []
        self._seen_keys = set()

    def send(self, order_id, idempotency_key=None):
        if idempotency_key is not None:
            if idempotency_key in self._seen_keys:
                return                      # a real provider ignores a repeated key
            self._seen_keys.add(idempotency_key)
        self.deliveries.append(order_id)


class FlakyStore:
    """mark_sent fails the first time, like a database that drops a connection."""

    def __init__(self):
        self.sent = set()
        self._failed_once = False

    def is_sent(self, order_id):
        return order_id in self.sent

    def mark_sent(self, order_id):
        if not self._failed_once:
            self._failed_once = True
            raise TransientError("connection reset by peer")
        self.sent.add(order_id)


def run_with_retries(task, *args, retries=3):
    for attempt in range(retries + 1):
        try:
            return task(*args)
        except TransientError:
            if attempt == retries:
                raise
