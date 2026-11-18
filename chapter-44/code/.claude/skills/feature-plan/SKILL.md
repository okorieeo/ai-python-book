---
name: feature-plan
description: Interview me about a feature, then write PLAN.md. Use when I ask to plan a feature before any code is written.
argument-hint: "<the feature in one sentence>"
disable-model-invocation: true
---
Plan this feature and write no code: $ARGUMENTS

1. Explore first. Read the code this will touch and the nearest similar feature. For a broad search, use a subagent so your own context stays clean.
2. If anything important is ambiguous (who may do it, what happens on failure, what is out of scope), ask me up to five focused questions BEFORE writing the plan. Do not guess.
3. Write PLAN.md following @prompts/templates/PLAN.template.md. Rules:
   - Every file under "Files" must exist, or be marked (new).
   - Each step is small enough to commit on its own and ends with "Done when:".
   - No more than twelve steps; if it needs more, say so and propose splitting it.
   - "Out of scope" must say what you are deliberately not doing.
4. Run `python3 tools/planlint.py PLAN.md --repo .` and fix every error it reports.
5. Stop. Wait for my review. Do not start building.
