python -m ai_verify smells sample/test_weak.py --target sample/billing_math.py

line 12: test_apply_discount_returns_int: every assertion is weak (only checks the type)  [trivial-assertions]
line 23: test_apply_discount_formula: the expected value is computed from the same inputs, so a wrong formula would be copied into the test. Write the expected number by hand  [mirror-expected]
line 31: test_apply_discount_runs: has no assertions: it passes unless the code crashes  [no-assertion]
line 43: test_overage_blocks_positive_when_over: every assertion is weak (only compares with zero)  [trivial-assertions]
line 51: test_trial_active: every assertion is weak (only checks truthiness)  [trivial-assertions]
line 55: test_trial_without_end: every assertion is weak (only checks falsiness)  [trivial-assertions]
line 59: test_prorate_credit_is_int: every assertion is weak (only checks the type)  [trivial-assertions]
line 63: test_prorate_credit_not_negative: every assertion is weak (only compares with zero)  [trivial-assertions]

8 smell(s) in sample/test_weak.py
