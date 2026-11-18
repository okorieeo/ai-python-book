---
name: new-component
description: Create a new UI component the way this project does it. Run as /new-component ComponentName.
disable-model-invocation: true
---
Create the component named in: $ARGUMENTS

1. Read CLAUDE.md and look in `src/components/ui/` for primitives to reuse. Say which ones you will use.
2. Put the component in `src/components/<area>/<Name>.tsx`. Make it a Server Component unless it needs state or browser APIs.
3. Use only design tokens (`bg-background`, `text-muted-foreground`, ...). No raw colors.
4. Add `<Name>.test.tsx` beside it covering: the main behavior, the empty or error state, and `expectNoA11yViolations` from `@/test-utils`.
5. Run `npm run typecheck` and `npm test`. Show me the output, not a summary.
6. Do not commit. List the files you created.
