# AI Chat frontend (Next.js App Router, TypeScript, Tailwind v4)

## Commands
- `npm run dev` starts the app on http://localhost:3000 (API on :8000)
- `npm run typecheck` and `npm test` must both pass before you say a task is done
- `npm run api:types` regenerates `src/lib/api/schema.d.ts` from `openapi/schema.yml`
- `npm run build` is the final check for anything that touches routes or config

## Architecture rules
- Server Components by default. Add `"use client"` only to the smallest component that needs state, effects or browser APIs.
- Every request to Django goes through `src/lib/api/client.ts`. Never call `fetch` for our API anywhere else.
- Never edit `src/lib/api/schema.d.ts` by hand: it is generated. If a type is wrong, the OpenAPI schema is wrong.
- Data fetching uses TanStack Query (`src/lib/api/queries.ts`), not `useEffect`.
- Forms use React Hook Form + a Zod schema in `src/lib/**/schemas.ts`.
- Server error text is never shown to users. Use `friendlyMessage()`.

## Design system
- Colors, radii and fonts live ONLY in `src/app/globals.css` tokens. Use semantic classes (`bg-background`, `text-muted-foreground`, `border-input`), never raw hex values or palette steps like `bg-blue-600`.
- Build on the primitives in `src/components/ui/`. Check there before writing a new button, input or label.
- Every interactive element needs a visible focus style and an accessible name.

## Gotchas
- `params` in route files is a Promise in this Next.js version: `const { id } = await params`.
- Model output is rendered with `react-markdown` WITHOUT `rehype-raw`. Never use `dangerouslySetInnerHTML`.
- Only `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL` are public. Never put a secret in a `NEXT_PUBLIC_*` variable.
- IMPORTANT: do not add dependencies without asking first. Say what the package does and why we cannot do it with what we have.
