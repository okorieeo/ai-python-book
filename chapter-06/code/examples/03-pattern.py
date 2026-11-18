def handle_payment_event(event_id: str, payload: dict) -> None:
    # PaymentEvent.event_id has a UNIQUE constraint in the database
    created = PaymentEvent.objects.get_or_create(event_id=event_id)[1]
    if not created:
        return                    # already processed: do nothing, still return 200
    grant_subscription(payload)
