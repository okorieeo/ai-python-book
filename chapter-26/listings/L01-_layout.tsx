import { Slot } from "expo-router";

import { UpdateBanner } from "@/src/release/UpdateBanner";
import { UpdateRequiredScreen } from "@/src/release/UpdateRequiredScreen";
import { useVersionGate } from "@/src/release/useVersionGate";

export default function RootLayout() {
  const { state } = useVersionGate();

  if (state.kind === "blocked") return <UpdateRequiredScreen gate={state} />;

  return (
    <>
      <UpdateBanner />
      <Slot />
    </>
  );
}
