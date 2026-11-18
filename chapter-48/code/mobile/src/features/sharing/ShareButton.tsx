import { ActivityIndicator, Pressable, Text } from "react-native";
import type { ExpiresIn, ShareLinkCreated } from "../../lib/sharing";
import { useShareLink } from "./useShareLink";

type Api = { createShareLink(id: string, e: ExpiresIn): Promise<ShareLinkCreated> };

export function ShareButton({ api, conversationId }: { api: Api; conversationId: string }) {
  const { share, busy, error } = useShareLink(api, conversationId);
  return (
    <>
      <Pressable accessibilityRole="button" accessibilityLabel="Share conversation" disabled={busy}
                 onPress={() => share("7d")} style={{ padding: 12 }}>
        {busy ? <ActivityIndicator /> : <Text>Share</Text>}
      </Pressable>
      {error ? <Text accessibilityRole="alert" style={{ color: "#B3261E" }}>{error}</Text> : null}
    </>
  );
}
