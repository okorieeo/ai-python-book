"""Money without mistakes: whole numbers of the smallest unit (kobo, pesewas, cents), never floats."""
from decimal import Decimal, DecimalException

from .errors import BadAmount

# currency -> (symbol, how many smallest units make one major unit). Paystack's documentation lists all of
# these with a factor of 100. Your Paystack account must be enabled for a currency before you charge in it.
CURRENCIES = {
    "NGN": ("\u20a6", 100),      # Nigerian naira, kobo
    "GHS": ("GH\u20b5", 100),    # Ghanaian cedi, pesewas
    "ZAR": ("R", 100),           # South African rand, cents
    "KES": ("KSh", 100),         # Kenyan shilling, cents
    "USD": ("$", 100),           # US dollar, cents
    "XOF": ("CFA", 100),         # West African CFA franc
}


MAX_MAJOR_UNITS = Decimal("1000000000")   # a billion: far above any real price, far below anything that overflows


def check_currency(currency: str) -> str:
    code = (currency or "").upper()
    if code not in CURRENCIES:
        raise ValueError(f"Unsupported currency: {currency!r}")
    return code


def to_subunit(amount, currency: str) -> int:
    """Convert an amount in major units ('5000', Decimal('49.99'), 5000) to whole smallest units.

    Floats are refused: 0.1 + 0.2 is not 0.3 in binary, and a payment amount must be exact. Pass a
    string or a Decimal. An amount with more decimals than the currency has (49.999) is an error, not
    something to round silently.
    """
    code = check_currency(currency)
    if isinstance(amount, (float, bool)) or amount is None:
        raise BadAmount("Pass the amount as a string, an int or a Decimal, never a float.")
    try:
        value = Decimal(str(amount).strip())
        if not value.is_finite() or abs(value) > MAX_MAJOR_UNITS:
            raise BadAmount(f"Not a sensible amount: {amount!r}")
        scaled = value * CURRENCIES[code][1]
    except DecimalException:
        raise BadAmount(f"Not a number: {amount!r}") from None
    if scaled != scaled.to_integral_value():
        raise BadAmount(f"{amount} has more decimals than {code} allows")
    return int(scaled)


def from_subunit(subunits: int, currency: str) -> Decimal:
    code = check_currency(currency)
    if isinstance(subunits, bool) or not isinstance(subunits, int):
        raise BadAmount("Smallest-unit amounts are whole numbers.")
    return Decimal(subunits) / CURRENCIES[code][1]


def format_money(subunits: int, currency: str) -> str:
    """'\u20a65,000.00' for display. Never use this text to compute anything."""
    code = check_currency(currency)
    return f"{CURRENCIES[code][0]}{from_subunit(subunits, code):,.2f}"
