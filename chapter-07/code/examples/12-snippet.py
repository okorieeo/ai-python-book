from django.db import transaction

def consume_credits(user_id: int, amount: int) -> None:
    with transaction.atomic():
        # Lock this user's row until the transaction ends; other requests for the same user wait here
        wallet = Wallet.objects.select_for_update().get(user_id=user_id)
        if wallet.balance < amount:
            raise InsufficientCredits()
        wallet.balance -= amount
        wallet.save(update_fields=["balance"])
