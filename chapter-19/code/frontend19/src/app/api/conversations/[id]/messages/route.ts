import { addMessage } from "@/lib/data";
import { apiError } from "@/lib/errors";

export async function POST(
  request: Request,
  ctx: RouteContext<"/api/conversations/[id]/messages">,
) {
  const { id } = await ctx.params;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return apiError(400, "invalid_json", "The request body is not valid JSON.");
  }
  const content =
    typeof body === "object" && body !== null && "content" in body
      ? (body as { content: unknown }).content
      : undefined;
  if (
    typeof content !== "string" ||
    content.trim() === "" ||
    content.length > 8000
  ) {
    return apiError(
      422,
      "validation_error",
      "The request contains invalid fields.",
      {
        content: ["Enter 1 to 8000 characters."],
      },
    );
  }

  const result = await addMessage(id, content.trim());
  if (!result) return apiError(404, "not_found", "Conversation not found.");
  return Response.json(result, { status: 201 });
}
