>>> report = reconcile(
...     ours=[Line("pay_a", 500000, "NGN", "succeeded"), Line("pay_b", 100000, "NGN", "succeeded"),
...           Line("pay_c", 250000, "NGN", "succeeded")],
...     gateway=[Line("pay_a", 500000, "NGN", "succeeded", fee_minor=7500), Line("pay_b", 90000, "NGN", "succeeded"),
...              Line("pay_d", 75000, "NGN", "succeeded")])
>>> report.matched
1
>>> [(d.kind.value, d.reference, d.detail) for d in report.discrepancies]
[('amount_mismatch', 'pay_b', '100000 vs 90000'),
 ('missing_at_gateway', 'pay_c', 'we have it, gateway does not'),
 ('missing_internal', 'pay_d', 'gateway has it, we do not')]
