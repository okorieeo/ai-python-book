<!-- Bug template: the symptom and the evidence matter more than your theory about the cause. -->
Fix <the symptom, in the user's words>.

Symptom and evidence: <what happens, how often, an error message or log line, the request id, steps to reproduce>.
Context: the suspect code is @path/to/file (function name). Read it and its tests first. Theory (may be wrong): <your guess>.

Work in this order:
1. Write a failing test that reproduces it in @path/to/test_file and show me it fails.
2. Fix the cause with the smallest change that makes it pass.

Constraints:
- Do not edit existing tests to make them pass; do not swallow the error.
- No schema or API-shape changes; if you think one is needed, stop and say why.

Done when: the new test failed before and passes after (show both runs), and <make check> passes.
