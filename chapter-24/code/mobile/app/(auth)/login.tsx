import { Link } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text } from "react-native";

import { describeError } from "../../src/api/errors";
import { useAuth } from "../../src/auth/AuthContext";
import { Button, ErrorText, Field, colors } from "../../src/ui";

export default function Login() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (busy) return; // ignore a second tap while the first is running
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
    } catch (e) {
      setError(describeError(e));
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={{ padding: 24, paddingTop: 96 }} keyboardShouldPersistTaps="handled">
        <Text style={{ fontSize: 28, fontWeight: "700", color: colors.ink, marginBottom: 24 }}>Sign in</Text>
        <Field label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" autoComplete="email"
          keyboardType="email-address" textContentType="username" />
        <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry
          autoComplete="current-password" textContentType="password" onSubmitEditing={submit} />
        {error ? <ErrorText>{error}</ErrorText> : null}
        <Button title="Sign in" onPress={submit} busy={busy} />
        <Link href="/register" style={{ textAlign: "center", marginTop: 16, color: colors.primary }}>
          Create an account
        </Link>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
