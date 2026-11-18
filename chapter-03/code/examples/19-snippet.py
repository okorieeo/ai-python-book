class Account:
    def __init__(self, owner: str, balance: float = 0.0) -> None:
        self.owner = owner           # attribute
        self.balance = balance

    def deposit(self, amount: float) -> None:       # method
        if amount <= 0:
            raise ValueError("Amount must be positive")
        self.balance += amount

    def __str__(self) -> str:
        return f"{self.owner}: {self.balance:.2f}"

acct = Account("Ada", 100)
acct.deposit(50)
print(acct)                  # Ada: 150.00
