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
