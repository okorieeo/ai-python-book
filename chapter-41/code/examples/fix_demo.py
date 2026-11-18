"""A bug report, a plausible-but-wrong fix, and the right fix, judged by three different tests.

Bug: split_evenly(100, 3) returns [33, 33, 33], so an invoice split three ways loses one cent.
The "plausible fix" below was written by hand to illustrate a common kind of wrong answer. It is not
a recording of any model.
"""


def buggy(total, parts):
    return [total // parts] * parts


def plausible_fix(total, parts):
    shares = [total // parts] * parts
    shares[-1] += total - sum(shares)  # the leftover goes on the last share
    return shares


def right_fix(total, parts):
    base, extra = divmod(total, parts)
    return [base + 1 if i < extra else base for i in range(parts)]


def reporters_test(f):          # what the person who found the bug checked
    return sum(f(100, 3)) == 100


def spec_test(f):               # what the documented behavior says: earlier shares get the extra units
    return f(100, 3) == [34, 33, 33] and f(10, 4) == [3, 3, 2, 2] and f(2, 5) == [1, 1, 0, 0, 0]


def property_test(f):           # must hold for every input
    return all(
        sum(f(t, p)) == t and max(f(t, p)) - min(f(t, p)) <= 1 and f(t, p) == sorted(f(t, p), reverse=True)
        for t in range(40) for p in range(1, 8)
    )


if __name__ == "__main__":
    tests = [("reporter's check (sum is 100)", reporters_test), ("documented examples", spec_test),
             ("property: all inputs", property_test)]
    print(f"{'version':<16}" + "".join(f"{name:<32}" for name, _ in tests))
    for label, fn in (("buggy", buggy), ("plausible fix", plausible_fix), ("right fix", right_fix)):
        print(f"{label:<16}" + "".join(f"{('pass' if t(fn) else 'FAIL'):<32}" for _, t in tests))
