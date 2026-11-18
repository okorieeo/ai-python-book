Show the assistant's reply as it streams in, using POST /api/v1/conversations/{id}/stream/.

Context: the event format (start, delta, done, error) is defined in @backend/ai/sse.py. The chat screen is @web/components/ChatWindow.tsx and the data hook is @web/lib/useChat.ts. Read all three first.

Constraints:
- Do not change the backend.
- A delta event can arrive split across two network chunks; the parser must handle that.
- An error event with partial: true must keep the text already shown and offer "Try again" beneath it.
- Cancel the request with an AbortController when the person leaves the page.
- No new dependencies.

Done when:
- Unit tests for the parser cover a delta split across two chunks and an error after partial text.
- A Playwright test mocks the stream with page.route and asserts the text appears progressively.
- `npm test` passes.
