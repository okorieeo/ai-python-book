import { useCallback, useState } from "react";
import { Share } from "react-native";
import type { ExpiresIn, ShareLinkCreated } from "../../lib/sharing";

type Api = { createShareLink(id: string, e: ExpiresIn): Promise<ShareLinkCreated> };

/** Creates a link, then hands it to the phone's own share sheet (AC-11). */
export function useShareLink(api: Api, conversationId: string) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const share = useCallback(
    async (expiresIn: ExpiresIn = "7d") => {
      setBusy(true);
      setError(null);
      try {
        const link = await api.createShareLink(conversationId, expiresIn);
        await Share.share({ message: link.url }); // iOS also accepts `url`; `message` works on both
      } catch (e) {
        setError(e instanceof Error ? e.message : "Something went wrong.");
      } finally {
        setBusy(false);
      }
    },
    [api, conversationId],
  );

  return { share, busy, error };
}
