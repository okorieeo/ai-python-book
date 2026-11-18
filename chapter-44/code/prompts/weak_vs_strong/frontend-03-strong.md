Add a login form at /login with email and password fields.

Context: follow @web/components/SignupForm.tsx, which already uses React Hook Form and Zod. Sign in through the existing authClient.login() in @web/lib/authClient.ts.

Constraints:
- Never store tokens in localStorage; the API route already sets an httpOnly cookie.
- A failed login shows one generic message and must not reveal whether the email or the password was wrong.
- Disable the submit button while the request is in flight.
- No new dependencies. Do not change SignupForm.

Done when React Testing Library tests show: an invalid email shows its message, a 401 shows the generic error, and the button is disabled while submitting. `npm test` passes.
