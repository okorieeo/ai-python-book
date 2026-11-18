# Chapter 41 — Using AI to Test and Debug: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Generating Tests with AI › What to give the assistant

The quality of the tests follows the quality of the request. A request like "write tests for this file" gets the easiest tests that pass. A request that includes the **contract** gets tests of behavior. Give it:

1. **The code**, and the existing test style (paste a test you like, so it matches your fixtures and naming).
2. **The rules in words**, including the ones the code cannot show: "money is whole cents; the discount is rounded half up; an invalid percentage must raise ValueError".
3. **A request for a list first.** Ask it to list the behaviors and edge cases it will test, so you can correct the list before any code exists.
4. **Expected values written out.** Ask for exact numbers worked out by hand, not computed with the same formula as the code.
5. **The failure cases**, not only the happy path: bad input, boundaries, empty values.
Here is the same request written two ways:

**a weak request**

```
"Write pytest tests for billing_math.py"
```

**a better request**

```
Write pytest tests for billing_math.py (attached). Rules the code must follow:
- Money is a whole number of cents. Never a float.
- apply_discount rounds the DISCOUNT half up, so 1005 at 10% gives 904, not 905.
- split_evenly must add up exactly and give earlier shares the extra cents.
- Invalid input raises ValueError.

First list every behavior and edge case you will cover. Then write the tests with the
expected values written out as literal numbers that you worked out by hand, not computed by
the code under test. Include the boundary of every range and every error path.
```


## Reviewing AI-Written Tests Critically › Fixing the tests

Now the same module, tested by someone who worked out the expected values by hand. The changes are mostly not clever. They are exact numbers, the edge of every range, every error path with its message, and one property that must hold for every input:

**sample/test_strong.py (excerpt)**

```
@pytest.mark.parametrize("price, percent, expected", [
    (1000, 10, 900),      # a whole discount: 100
    (1005, 10, 904),      # 100.5 rounds half UP to 101
    (999, 50, 499),       # 499.5 rounds up to 500
    (1, 50, 0),           # 0.5 rounds up to 1
])
def test_apply_discount_exact_values(price, percent, expected):
    assert apply_discount(price, percent) == expected

@pytest.mark.parametrize("total", range(0, 40))
@pytest.mark.parametrize("parts", range(1, 8))
def test_split_evenly_never_loses_money_and_is_fair(total, parts):
    shares = split_evenly(total, parts)
    assert sum(shares) == total
    assert max(shares) - min(shares) <= 1
    assert shares == sorted(shares, reverse=True)

def test_trial_is_active_before_the_end_and_not_at_or_after_it():
    end = datetime(2026, 2, 1, 12)
    assert is_trial_active(end - timedelta(seconds=1), end) is True
    assert is_trial_active(end, end) is False
    assert is_trial_active(end + timedelta(seconds=1), end) is False
```

**bash terminal**

```bash
python -m ai_verify smells sample/test_strong.py --target sample/billing_math.py
python -m ai_verify mutate --project sample --module billing_math.py \
  --cmd "python -m pytest -x -q -p no:cacheprovider test_strong.py"

0 smell(s) in sample/test_strong.py

Mutation testing: billing_math.py
  mutants: 56   killed: 55   survived: 1   score: 98%   (24s)
  Survivors (a bug like this would pass your tests):
    line  23: 100 -> 101
```

No smells, and a mutation score of **98 percent**, with the same 100 percent coverage. The first time I ran this on the reviewed suite, it scored 96 percent and found two survivors, and both are instructive:

- **A real gap.**  `line 71: 0 -> 1` meant a period of exactly one second was never tested: even careful hand-written tests missed a boundary. Adding two cases for it killed that mutant. Mutation testing finds gaps that human reviewers miss, too.
- **An equivalent mutant.**  `line 23: 100 -> 101` changes the rounding constant in `(price * percent * 2 + 100) // 200`, yet **no input can tell the difference**: the value being rounded is always even, so adding 101 instead of 100 never changes the answer. A survivor like this is not a missing test. It is noise, and the only way to know is to read it.
> **Read every survivor, and expect some to be harmless**
>
> A survivor means one of three things: your tests have a gap (write the test), the mutant is **equivalent** (the change cannot alter behavior, as above), or the code is dead (delete it). Do not chase 100 percent. A score in the high eighties or nineties on important, risky code is a strong result, and the survivors you have read and understood are the point of the exercise. Mutation testing is also slow, because it runs your tests once per mutant: use it on the code where a bug costs money (billing, permissions, rounding), not on the whole project, and run it occasionally rather than on every commit.


## Reviewing AI-Written Tests Critically › A real example: the tests from Chapter 35

To check that this works beyond a toy, I ran the tool on a module I wrote earlier, Chapter 35's `billing/pricing.py`, against the 11 tests written for it. They had **98 percent line coverage**. This is the real result (the command is the one from Step 8 of the hands-on):

**bash terminal**

```bash
python -m ai_verify mutate --project chapter_35_code --module billing/pricing.py \
  --cmd "python manage.py test billing.tests.test_pricing"

Mutation testing: billing/pricing.py
  mutants: 79   killed: 67   survived: 12   score: 85%   (43s)
  Survivors (a bug like this would pass your tests):
    line  23: 0 -> 1
    line  23: < -> <=
    line  37: 1 -> 2
    line  37: 12 -> 13
    line  37: return None instead of the value
    line  45: True -> False
    line  63: 0 -> 1
    line  66: 0 -> 1
    line 100: 0 -> 1
    line 100: <= -> <
    line 105: 1000000 -> 1000001
    line 117: 10000 -> 10001
```

An 85 percent score on tests I had reviewed carefully is a reminder that nobody is exempt. Reading the 12 survivors against the code: the two worth fixing are `line 23` (`format_money` is never tested with zero, so a bug that printed `-$0.00` would pass) and `line 37` (the yearly billing interval, twelve months, is never tested anywhere). The rest are equivalent or low-value: `frozen=True` on a dataclass, an early `break` that only saves time, and a constant that is divided away. I have left Chapter 35 as delivered so that you can reproduce these numbers, and closing the gaps is Exercise 5. That is the usual shape of a mutation result: a short list that is worth reading, and a few items that are not.


## Bug Reports and Prompts That Get Useful Fixes › A tool that builds the report

Assembling that by hand each time is tedious, and it is exactly when you are tired that you forget to remove the key from the log. `ai_verify bugreport` builds the report, trims the traceback, and **redacts secrets and personal data** before anything leaves your machine. Here it is on a real failure. The script below fails because of a trailing comma in a JSON string, and the string contains a (fake) API key and an email address:

**examples/failing_loader.py**

```
import json

def load_settings(text):
    return json.loads(text)

def main():
    text = '{\n  "api_key": "sk-ant-FAKEKEY1234567890abcdef",\n  "owner": "ada@example.com",\n}\n'
    return load_settings(text)

if __name__ == "__main__":
    main()
```

**bash terminal**

```bash
python examples/failing_loader.py 2> traceback.txt
python -m ai_verify bugreport \
  --title "load_settings crashes on settings.json" \
  --expected "load_settings returns a dict of my settings" \
  --actual "json.decoder.JSONDecodeError is raised and the app will not start" \
  --steps "Call load_settings() on the text of settings.json" \
  --traceback traceback.txt --code examples/failing_loader.py \
  --tried "Checked the file encoding; reading the file with open() works" \
  --constraints "Keep the function signature. No new dependencies." --package pytest
```

**output (real)**

```text
# load_settings crashes on settings.json

## Environment
Python 3.12.3 on Linux, pytest 9.2.0

## What I expected
load_settings returns a dict of my settings

## What happened instead
json.decoder.JSONDecodeError is raised and the app will not start

## Smallest way to reproduce
Call load_settings() on the text of settings.json (copied into examples/failing_loader.py)

## Error (trimmed)
```
Traceback (most recent call last):
  File "/home/[user]/work/chapter_41_code/examples/failing_loader.py", line 14, in <module>
    main()
  File "/home/[user]/work/chapter_41_code/examples/failing_loader.py", line 10, in main
    return load_settings(text)
           ^^^^^^^^^^^^^^^^^^^
  File "/home/[user]/work/chapter_41_code/examples/failing_loader.py", line 5, in load_settings
    return json.loads(text)
           ^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/json/__init__.py", line 346, in loads
    return _default_decoder.decode(s)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/json/decoder.py", line 337, in decode
    obj, end = self.raw_decode(s, idx=_w(s, 0).end())
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/json/decoder.py", line 353, in raw_decode
    obj, end = self.scan_once(s, idx)
               ^^^^^^^^^^^^^^^^^^^^^^
json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 4 column 1 (char 79)
```

## Relevant code
```python
import json

def load_settings(text):
    return json.loads(text)

def main():
    text = '{\n  "api_key": "[REDACTED_API_KEY]",\n  "owner": "[REDACTED_EMAIL]",\n}\n'
    return load_settings(text)

if __name__ == "__main__":
    main()
```

## What I already tried
Checked the file encoding; reading the file with open() works

## Constraints
Keep the function signature. No new dependencies.

## What I would like from you
1. List the most likely causes, most likely first, and say what evidence would confirm each.
2. Write a failing test that reproduces the problem, before proposing any fix.
3. Propose the smallest change that makes that test pass, and say what else it could affect.
4. Tell me which parts of your answer you could not verify from what I gave you.
```

Look at what happened to the code section: the fake key became `[REDACTED_API_KEY]` and the email `[REDACTED_EMAIL]`, and the file paths lost the username. The tool removes these patterns: Anthropic-style and similar API keys, AWS keys, JWTs, bearer tokens and `password=` style assignments, passwords inside database URLs, email addresses, Nigerian-format and international phone numbers, long digit runs that look like card numbers, and home-folder paths. The rules are a short list of regular expressions:

**ai_verify/bugreport.py (the redaction function)**

```
def redact(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text
```

> **Redaction is a safety net, not a guarantee**
>
> Patterns cannot know what is secret in your system: an internal hostname, a customer's name, an order number, or a key with an unusual format will pass straight through. Always read the report before you paste it. When in doubt, replace the real value with an obvious fake yourself. For traceback trimming, the tool keeps your own frames and the last few library frames, folds the rest into "(n library frames not shown)", and always keeps the final error line, which is the part people most often cut off.


## AI Code Review, Refactoring and Documentation › Refactoring

**Refactoring** means changing how code is written without changing what it does. Assistants are happy to "clean up" code, and that is exactly the danger: a tidy-looking change can alter behavior at an edge that nobody remembered. A safe refactor depends on tests that would notice. Here is a real demonstration. An assistant is asked to "simplify" `is_trial_active`, and changes `now < trial_end` to `now <= trial_end`. (It looks like an innocent tweak; I made the change by hand for this demonstration.) Both test suites from section 41.3 judge it:

**bash terminal**

```bash
weak suite:   18 passed in 0.02s
strong suite: 1 failed, 318 passed in 0.17s
E       assert True is False
FAILED test_strong.py::test_trial_is_active_before_the_end_and_not_at_or_after_it
```

**The weak suite passes all 18 tests, and the strong suite fails one.** The weak suite would have approved a change that lets a trial last one moment longer than promised. This is the point of the whole chapter in one result: the safety of a refactor is exactly the quality of the tests beneath it. A safe routine:

1. **First make sure the tests are good enough to refactor under.** Run the mutation check on the function. If survivors cluster in the code you are about to change, add tests first.
2. **Pin the current behavior.** If there are no tests, write **characterization tests**: tests that record what the code does now, for a range of inputs. They are not proof of correctness, but they tell you whether the refactor changed anything.
3. **Ask for a plan, then small steps.** One rename or one extraction at a time, running the tests after each. A single rewrite of an entire file is impossible to review.
4. **Do not change tests and code in the same step.** If you must edit a test to make a refactor pass, you have changed behavior, and you should know it.
5. **Read the diff.** A refactor that touches files you did not mention deserves suspicion.

## AI Code Review, Refactoring and Documentation › Documentation

Documentation is a good fit for an assistant: it is time-consuming and well structured. The risk is documentation that is **fluent and wrong**: a docstring that describes a parameter that does not exist, or an example whose output is invented. The cure is to make the examples **run**. In Python, an example written as a doctest is executed by the test runner, so documentation that has drifted from the code fails a test. The sample module's docstrings contain such examples:

**bash terminal**

```bash
python -m pytest --doctest-modules sample/billing_math.py

.....                                                                    [100%]
5 passed in 0.01s
```

Now suppose a documentation pass "corrects" one example to say 905 instead of 904. Run on that version, the real output is:

**bash terminal (after the wrong edit)**

```bash
012 Price after a percentage discount. The discount is rounded half up.
013
014     >>> apply_discount(1000, 10)
015     900
016     >>> apply_discount(1005, 10)
Expected:
    905
Got:
    904
FAILED billing_math.py::billing_math.apply_discount
```

The documentation now disagrees with the code, and the build says so. For other kinds of documentation: ask the assistant to write it **from the code you paste**, tell it who the reader is, and then check every command and example by running it. In a project, record that a README or docstring was drafted with help, and review it with the same care as code. Commit messages and pull request descriptions are another place assistants save time: give them the diff, and check that the description matches what really changed.


## What AI Gets Wrong, and How to Verify Its Output › Invented names: a checker that you can run

A common failure is code that calls something that does not exist. `ai_verify imports` parses a file, imports the modules it uses, and checks every import, attribute chain and keyword argument against what is **actually installed**. It never runs your code. Here is a snippet of the kind an assistant might write (it was written by hand for this chapter, and it reads well):

**examples/ai_snippet.py**

```
"""Code of the kind an assistant might write: it reads well, and four things in it do not exist.

(Written by hand for Chapter 41 to show the patterns. It is not a recording of any model.)
"""
import json
import os.path

from django.db import models
from django.db.models import CheckConstraint, Q
from django.utils.timezone import utcnow

def load_settings(path):
    if not os.path.exists_file(path):
        return {}
    with open(path) as handle:
        return json.parse(handle.read())

class Account(models.Model):
    balance_minor = models.BigIntegerField()

    class Meta:
        constraints = [
            CheckConstraint(check=Q(balance_minor__gte=0), name="balance_not_negative"),
        ]

def stamp():
    return utcnow()
```

**bash terminal**

```bash
python -m ai_verify imports examples/ai_snippet.py

line 10: error: 'django.utils.timezone' has no name 'utcnow'  [missing-name]
line 14: error: 'os.path' has no attribute 'exists_file'  [missing-attribute]
line 17: error: 'json' has no attribute 'parse'  [missing-attribute]
line 25: error: CheckConstraint() does not accept the keyword 'check' in the installed version  [bad-keyword]

4 error(s), 0 warning(s) in examples/ai_snippet.py
```

Four problems, each with a line number. Notice the last one: `CheckConstraint(check=...)` was the correct spelling in older Django, and the installed version no longer accepts it. The tool found that by reading the real function signature, which is exactly the kind of mistake you get from advice written for a different version. The corrected snippet gets a clean result:

**bash terminal**

```bash
python -m ai_verify imports examples/valid_snippet.py

0 error(s), 0 warning(s) in examples/valid_snippet.py
```

The core idea is small. For each name the code uses, look it up with `getattr`, but only trust a miss where Python itself can be trusted. Modules and plain classes qualify. Classes built by a metaclass (Django models, enums) get attributes at run time, so a missing one proves nothing:

**ai_verify/hallucination.py (excerpt)**

```
def _checkable_container(obj: Any) -> bool:
    """Only report a missing attribute where Python itself can be trusted about it."""
    if isinstance(obj, ModuleType):
        return True
    # A plain class. Classes built by a metaclass (Django models, enums, ORMs) get
    # attributes at run time, so a missing one proves nothing.
    return inspect.isclass(obj) and type(obj) is type
```


## What AI Gets Wrong, and How to Verify Its Output › Tools lie too: the false-alarm lesson

When I first ran this checker over the code from Chapters 27, 30 and 35, to confirm that it did not raise false alarms, it reported a lot:

**first run (real): the checker run from the wrong place**

```
TOTAL: 60 files, 65 errors, 7 warnings
```

Every one was a false alarm. The checker could not import my own modules because the project's folder was not on the Python path (so `from ai_lab.catalog import ...` looked like a missing module), and it could not import Django modules because Django's settings were not configured. A tool that cries wolf gets ignored, so I fixed both causes: the checker now tolerates lookups that need configuration, and it has two options, `--root` and `--django-settings`, that set up your project first. With the project set up properly, the same check over the same code gives:

**second run (real)**

```
Chapter 27 (ai_lab): 14 files, 0 errors, 0 warnings
Chapter 30 (agent_kit): 14 files, 0 errors, 0 warnings
Chapter 35 (billing): 32 files, 0 errors, 0 warnings
TOTAL: 60 files, 0 errors, 0 warnings
```

Zero findings across 60 files. Two lessons. First, **run the checker from your project root**, with your settings configured. Second, treat any tool's output, including an assistant's, as evidence to be judged, never as a verdict. This checker has real limits: it cannot see attributes of objects that only exist at run time (the result of a function call, a model instance), so a clean result means "no obvious invention", not "correct". A type checker (Chapter 42) catches many more of these, and actually running the code catches the rest.


## Common Mistakes When Using AI to Test and Debug

| **Mistake** | **Consequence** | **Better** |
|---|---|---|
| Judging tests by coverage | Fully "covered" code with no protection | Check with mutation testing and read the survivors |
| Merging AI-written tests unread | Trivial assertions and mirrors protect nothing | Run `smells`, and ask of each test: would it fail if the code were wrong? |
| Asking for tests of code that already has a bug | The tests protect the bug | Give the rules in words and write expected values from the requirement |
| Accepting a fix without a failing test | A plausible but wrong fix is merged | Reproduce, write the failing test, then fix |
| Letting the assistant loosen a failing test | The test now passes, and the bug is still there | Change a test only when the requirement changed |
| Judging a fix by one example | It passes the example and fails the rest | Add a property that must hold for all inputs |
| Pasting secrets and customer data | A leak you cannot take back | Redact, use fake values, follow your policy (Chapter 34) |
| Running `pip install` on a suggested name | A missing or malicious package | Check the name with `ai_verify package` first |
| Asking for a rewrite instead of small steps | A diff nobody can review | A plan first, then one small change at a time |
| Reviewing AI code in the same conversation | It agrees with itself | Use a fresh conversation, and a human reviewer |
| Trusting the explanation because it is fluent | A confident wrong cause | Reproduce it, and ask what evidence would confirm the cause |
| Trusting a tool's output blindly | False alarms or false comfort | Treat every tool, including an assistant, as evidence to be judged |
| Stating no versions | Advice for the wrong version of a library | Put versions in every prompt and report |
| Chasing a 100 percent mutation score | Time wasted on equivalent mutants | Read survivors on risky code; accept harmless ones |
| Documentation nobody runs | Examples that have drifted from the code | Write examples as doctests, so they fail when they are wrong |
