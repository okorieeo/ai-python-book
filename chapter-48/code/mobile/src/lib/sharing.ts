import createClient from "openapi-fetch";
import type { components, paths } from "./generated/schema";

export type ShareLinkCreated = components["schemas"]["ShareLinkCreated"];
export type ExpiresIn = NonNullable<components["schemas"]["ShareLinkCreate"]["expires_in"]>;

/** getToken comes from the secure-storage helper built in Chapter 47 (expo-secure-store). */
export function makeSharingApi(baseUrl: string, getToken: () => Promise<string | null>) {
  const client = createClient<paths>({ baseUrl });

  async function authHeaders() {
    const token = await getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  return {
    async createShareLink(conversationId: string, expiresIn: ExpiresIn): Promise<ShareLinkCreated> {
      const { data, response } = await client.POST("/api/v1/conversations/{conversation_id}/share/", {
        params: { path: { conversation_id: conversationId } },
        body: { expires_in: expiresIn },
        headers: await authHeaders(),
      });
      if (!data) throw new Error(response.status === 429 ? "Too many links today. Try again tomorrow." : "Could not create the link.");
      return data;
    },
  };
}
