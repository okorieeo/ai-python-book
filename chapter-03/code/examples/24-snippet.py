class InsufficientTokensError(Exception):
    """Raised when a user has no tokens left."""

def use_tokens(balance: int, amount: int) -> int:
    if amount > balance:
        raise InsufficientTokensError(f"Need {amount}, have {balance}")
    return balance - amount

try:
    use_tokens(100, 500)
except InsufficientTokensError as error:
    print("Upgrade your plan:", error)
