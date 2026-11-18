import { api, ApiError, unwrap } from "./client";
import type { components } from "./generated/schema";

export type ShareLink = components["schemas"]["ShareLink"];
export type ShareLinkCreated = components["schemas"]["ShareLinkCreated"];
export type ExpiresIn = NonNullable<components["schemas"]["ShareLinkCreate"]["expires_in"]>;

export async function createShareLink(conversationId: string, expiresIn: ExpiresIn): Promise<ShareLinkCreated> {
  return unwrap(
    await api.POST("/api/v1/conversations/{conversation_id}/share/", {
      params: { path: { conversation_id: conversationId } },
      body: { expires_in: expiresIn },
    }),
  );
}

export async function listShareLinks(conversationId: string): Promise<ShareLink[]> {
  return unwrap(
    await api.GET("/api/v1/conversations/{conversation_id}/share/", {
      params: { path: { conversation_id: conversationId } },
    }),
  );
}

export async function revokeShareLink(conversationId: string, linkId: string): Promise<void> {
  const result = await api.DELETE("/api/v1/conversations/{conversation_id}/share/{link_id}/", {
    params: { path: { conversation_id: conversationId, link_id: linkId } },
  });
  if (!result.response.ok) throw new ApiError(result.response.status, "Could not revoke the link.");
}
