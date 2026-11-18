Build the /pricing page showing the Free, Pro and Team plans returned by GET /api/v1/plans/.

Context: reuse the card in @web/components/PlanCard.tsx and the price formatting in @web/lib/format.ts (formatMoney). Copy the layout and heading structure of @web/app/(marketing)/about/page.tsx. The plan data shape is documented in @docs/api-conventions.md.

Constraints:
- Fetch in a Server Component; the page itself must not need client-side JavaScript to show prices.
- No new dependencies; use the existing Tailwind tokens.
- Accessible: exactly one h1, and each button is findable by its name.
- Do not implement checkout. The button only calls the existing onChoose prop; checkout is a separate step.
- If the fetch fails, show the existing ErrorState component.

Done when:
- Component tests cover three plans rendered and the error state.
- A Playwright test in web/e2e/pricing.spec.ts asserts three "Choose" buttons are visible.
- `npm test` and `npx tsc --noEmit` pass.
