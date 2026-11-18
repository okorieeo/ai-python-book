<!-- Refactor template: behaviour must not change, so the proof is the tests that already exist. -->
Refactor <what> in @path/to/module so that <the specific structural goal: one responsibility per function, no import of X from Y, ...>.

Context: the current behaviour is pinned by @path/to/existing_tests. Read them first and run them to confirm they pass BEFORE you change anything.

Constraints:
- Behaviour must not change: do not edit, delete or loosen any existing test.
- Public function names and signatures stay the same: <list them>.
- Do it in steps of at most <N> files each, and tell me when you have finished one so I can commit it.
- Out of scope: new features, renames outside this module, formatting-only changes.

Done when the same tests pass unchanged after each step, `make check` passes, and you list what moved where.
