"""Invoice numbers, tax arithmetic and credit notes. Issued invoices are never edited."""
from __future__ import annotations

from dataclasses import dataclass

from .money import Money


@dataclass(frozen=True)
class Line:
    description: str
    quantity: int
    unit_price: Money     # net if tax is added on top, gross if prices include tax

    @property
    def total(self) -> Money:
        return Money(self.unit_price.amount_minor * self.quantity, self.unit_price.currency)


@dataclass(frozen=True)
class Totals:
    net: Money
    tax: Money
    gross: Money


def invoice_number(prefix: str, year: int, sequence: int) -> str:
    if sequence < 1:
        raise ValueError("sequence starts at 1")
    return f"{prefix}-{year}-{sequence:06d}"


def totals_for(lines: list[Line], rate_bp: int, *, prices_include_tax: bool) -> Totals:
    """Tax is computed once on the invoice total, not per line, so rounding cannot drift."""
    if not lines:
        raise ValueError("an invoice needs at least one line")
    currency = lines[0].unit_price.currency
    subtotal = Money(0, currency)
    for line in lines:
        subtotal = subtotal + line.total
    if prices_include_tax:
        # tax = gross * rate / (1 + rate)
        tax = Money(round_half_up(subtotal.amount_minor * rate_bp, 10000 + rate_bp), currency)
        return Totals(net=subtotal - tax, tax=tax, gross=subtotal)
    tax = subtotal.basis_points(rate_bp)
    return Totals(net=subtotal, tax=tax, gross=subtotal + tax)


def round_half_up(numerator: int, denominator: int) -> int:
    return (2 * numerator + denominator) // (2 * denominator)


def credit_note_totals(original: Totals, refund_gross: Money) -> Totals:
    """Split a refund into net and tax in the same proportion as the invoice. The parts always add up."""
    if refund_gross.amount_minor > original.gross.amount_minor:
        raise ValueError("a credit note cannot exceed the invoice")
    if original.gross.amount_minor == 0:
        return Totals(refund_gross, Money(0, refund_gross.currency), refund_gross)
    tax = Money(round_half_up(original.tax.amount_minor * refund_gross.amount_minor,
                              original.gross.amount_minor), refund_gross.currency)
    return Totals(net=refund_gross - tax, tax=tax, gross=refund_gross)
