import { Link } from "expo-router";
import { Pressable, Text, View } from "react-native";

import { useAuth } from "@/lib/auth";
import { registerForPush } from "@/lib/notifications";

export default function Home() {
  const { signOut } = useAuth();
  return (
    <View style={{ flex: 1, justifyContent: "center", padding: 24, gap: 16 }}>
      <Link href="/chat/1">Open chat 1</Link>
      <Link href="/scan">Scan a code</Link>
      <Pressable accessibilityRole="button" onPress={() => void registerForPush()}>
        <Text>Turn on notifications</Text>
      </Pressable>
      <Pressable accessibilityRole="button" onPress={() => void signOut()}>
        <Text>Sign out</Text>
      </Pressable>
    </View>
  );
}
