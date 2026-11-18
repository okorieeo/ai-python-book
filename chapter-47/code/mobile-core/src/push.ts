/**
 * Decide where a tapped push notification should take the user.
 *
 * The data in a notification is input from outside your app. Never navigate to a path or URL taken
 * from it. Instead, accept a small set of known types with strictly shaped ids, and build the
 * route yourself. Anything else returns null, which means "just open the app".
 */
const ID = /^\d{1,12}$/;

function idOf(value: unknown): string | null {
  const text = typeof value === "number" ? String(value) : value;
  return typeof text === "string" && ID.test(text) ? text : null;
}

export function routeForNotification(data: unknown): string | null {
  if (typeof data !== "object" || data === null) return null;
  const d = data as Record<string, unknown>;
  switch (d.type) {
    case "chat_message": {
      const id = idOf(d.conversation_id);
      return id ? `/chat/${id}` : null;
    }
    case "invoice_paid": {
      const id = idOf(d.invoice_id);
      return id ? `/settings/billing/invoices/${id}` : null;
    }
    case "usage_limit":
      return "/settings/billing";
    default:
      return null;
  }
}
