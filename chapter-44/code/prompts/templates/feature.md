<!-- Feature template: copy, fill every line, delete what does not apply. If you cannot fill a line, that is the thing to find out first. -->
[Goal] Add / Build / Show ... (the outcome, as an action, one sentence).

Context: follow the pattern in @path/to/similar_file and read @path/to/relevant_file first. Docs: <url or @docs/file.md>.

Constraints:
- Reuse: <the existing helper, component or mixin to use>.
- Do not change: <models, public API shape, unrelated modules>.
- No new dependencies. <Other limits: performance, accessibility, security rule.>
- Out of scope: <the thing that is tempting but belongs to a later step>.

Done when:
- Tests: <which new tests, covering which cases, in which file>.
- Commands that must pass: <make check / pytest path / npm test / npx tsc --noEmit>.
- Show me the output, then stop.
