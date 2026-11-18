"""Money as integers in the smallest unit. Floats never touch an amount."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Digits after the decimal point. Unknown currencies are refused, not guessed.
EXPONENTS = {
    "NGN": 2, "GHS": 2, "ZAR": 2, "KES": 2, "USD": 2, "EUR": 2, "GBP": 2,
    "JPY": 0, "KRW": 0, "XOF": 0, "XAF": 0, "RWF": 0,
}


class MoneyError(ValueError):
    pass


@dataclass(frozen=True, order=False)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self):
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise MoneyError("amount_minor must be an int (kobo, cents), never a float")
        if self.currency not in EXPONENTS:
            raise MoneyError(f"unsupported currency {self.currency!r}")

    @classmethod
    def from_major(cls, amount: str | int | Decimal, currency: str) -> "Money":
        """Money.from_major("5000.50", "NGN") -> 500050 kobo. Floats are rejected on purpose."""
        if isinstance(amount, float):
            raise MoneyError("pass a string or Decimal, not a float: 0.1 + 0.2 != 0.3")
        if currency not in EXPONENTS:
            raise MoneyError(f"unsupported currency {currency!r}")
        value = Decimal(str(amount)) * (Decimal(10) ** EXPONENTS[currency])
        if value != value.to_integral_value():
            raise MoneyError(f"{amount} has more decimals than {currency} allows")
        return cls(int(value), currency)

    def to_major(self) -> Decimal:
        return Decimal(self.amount_minor) / (Decimal(10) ** EXPONENTS[self.currency])

    def _same(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise MoneyError(f"cannot mix {self.currency} and {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def is_positive(self) -> bool:
        return self.amount_minor > 0

    def basis_points(self, bp: int) -> "Money":
        """bp=750 is 7.5%. Rounds half up, in integer arithmetic."""
        cents = (Decimal(self.amount_minor) * bp / Decimal(10000)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return Money(int(cents), self.currency)

    def __str__(self) -> str:
        places = EXPONENTS[self.currency]
        return f"{self.currency} {self.to_major():,.{places}f}"
