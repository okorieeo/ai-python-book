"""The one required check. Reads the results of every job it depends on and decides pass or fail.

Why it exists: branch protection needs a FIXED list of required checks. Jobs that are skipped on purpose (the
web job when only the backend changed) would leave a required check "pending" for ever. This job always runs,
treats "skipped" as fine and "failed", "cancelled" or "missing" as not fine.
"""

import json
import os
import sys

OK = {"success", "skipped"}


def evaluate(needs: dict[str, dict]) -> tuple[bool, list[str]]:
    problems = []
    if "changes" not in needs:
        problems.append("the 'changes' job is missing from needs")
    elif needs["changes"].get("result") != "success":
        problems.append(f"changes: {needs['changes'].get('result')} (a skipped job cannot be trusted here)")
    for name, info in needs.items():
        if name == "changes":
            continue
        result = info.get("result")
        if result not in OK:
            problems.append(f"{name}: {result}")
    return (not problems, problems)


def main() -> int:
    needs = json.loads(os.environ["NEEDS_JSON"])
    passed, problems = evaluate(needs)
    for name, info in sorted(needs.items()):
        print(f"{name:10} {info.get('result')}")
    if not passed:
        print("\nNOT OK:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print("\nAll required jobs passed (or were skipped because nothing they cover changed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
