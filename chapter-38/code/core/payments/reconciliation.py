"""Compare what we think happened with what the gateway says happened."""
from __future__ import annotations

import enum
from collections import Counter
from dataclasses import dataclass, field


class Kind(enum.StrEnum):
    MISSING_INTERNAL = "missing_internal"        # gateway took money, we have no success
    MISSING_AT_GATEWAY = "missing_at_gateway"    # we say succeeded, gateway has no such payment
    AMOUNT_MISMATCH = "amount_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    STATUS_MISMATCH = "status_mismatch"
    DUPLICATE_REFERENCE = "duplicate_reference"


@dataclass(frozen=True)
class Line:
    reference: str
    amount_minor: int
    currency: str
    status: str                  # succeeded | refunded | partially_refunded | failed
    refunded_minor: int = 0
    fee_minor: int = 0


@dataclass(frozen=True)
class Discrepancy:
    kind: Kind
    reference: str
    detail: str


@dataclass
class Report:
    matched: int = 0
    discrepancies: list[Discrepancy] = field(default_factory=list)
    gateway_total: dict[str, int] = field(default_factory=dict)
    internal_total: dict[str, int] = field(default_factory=dict)
    fees: dict[str, int] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.discrepancies

    def count(self) -> Counter:
        return Counter(d.kind for d in self.discrepancies)


def reconcile(internal: list[Line], gateway: list[Line]) -> Report:
    """internal: our payments in the period that we believe settled. gateway: the gateway's settled lines."""
    report = Report()
    for name, lines in (("internal", internal), ("gateway", gateway)):
        dupes = [r for r, n in Counter(l.reference for l in lines).items() if n > 1]
        for ref in dupes:
            report.discrepancies.append(Discrepancy(Kind.DUPLICATE_REFERENCE, ref, f"appears twice in {name} data"))
    ours = {l.reference: l for l in internal}
    theirs = {l.reference: l for l in gateway}

    for ref, line in theirs.items():
        report.gateway_total[line.currency] = report.gateway_total.get(line.currency, 0) + line.amount_minor - line.refunded_minor
        report.fees[line.currency] = report.fees.get(line.currency, 0) + line.fee_minor
    for ref, line in ours.items():
        report.internal_total[line.currency] = report.internal_total.get(line.currency, 0) + line.amount_minor - line.refunded_minor

    for ref in sorted(set(ours) | set(theirs)):
        mine, other = ours.get(ref), theirs.get(ref)
        if mine is None:
            report.discrepancies.append(Discrepancy(Kind.MISSING_INTERNAL, ref, "gateway has it, we do not"))
        elif other is None:
            report.discrepancies.append(Discrepancy(Kind.MISSING_AT_GATEWAY, ref, "we have it, gateway does not"))
        elif mine.currency != other.currency:
            report.discrepancies.append(Discrepancy(Kind.CURRENCY_MISMATCH, ref, f"{mine.currency} vs {other.currency}"))
        elif mine.amount_minor != other.amount_minor:
            report.discrepancies.append(Discrepancy(Kind.AMOUNT_MISMATCH, ref, f"{mine.amount_minor} vs {other.amount_minor}"))
        elif mine.status != other.status or mine.refunded_minor != other.refunded_minor:
            report.discrepancies.append(Discrepancy(
                Kind.STATUS_MISMATCH, ref, f"{mine.status}/{mine.refunded_minor} vs {other.status}/{other.refunded_minor}"))
        else:
            report.matched += 1
    return report
