import { createConversation, listConversations } from "@/lib/data";

export async function GET() {
  return Response.json({ results: await listConversations() });
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as { title?: unknown };
  const title = typeof body.title === "string" ? body.title : undefined;
  return Response.json(await createConversation(title), { status: 201 });
}
