import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";

import { AiConsentGate } from "./AiConsentGate";

const store: Record<string, string> = {};
jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(async (k: string) => store[k] ?? null),
  setItemAsync: jest.fn(async (k: string, v: string) => { store[k] = v; }),
}));

beforeEach(() => { for (const k of Object.keys(store)) delete store[k]; });

const Protected = () => <Text>the chat screen</Text>;

describe("AiConsentGate", () => {
  it("asks first and shows nothing behind it until the person agrees", async () => {
    await render(<AiConsentGate onDecline={() => {}}><Protected /></AiConsentGate>);
    expect(await screen.findByText("Before you chat")).toBeTruthy();
    expect(screen.queryByText("the chat screen")).toBeNull();
  });

  it("remembers a yes, and shows the chat", async () => {
    await render(<AiConsentGate onDecline={() => {}}><Protected /></AiConsentGate>);
    fireEvent.press(await screen.findByText("I agree"));
    await waitFor(() => expect(screen.getByText("the chat screen")).toBeTruthy());
    expect(store["ai-consent-v1"]).toBe("yes");
  });

  it("does not ask again once consent is stored", async () => {
    store["ai-consent-v1"] = "yes";
    await render(<AiConsentGate onDecline={() => {}}><Protected /></AiConsentGate>);
    await waitFor(() => expect(screen.getByText("the chat screen")).toBeTruthy());
    expect(screen.queryByText("Before you chat")).toBeNull();
  });

  it("calls onDecline and stores nothing when the person says not now", async () => {
    const onDecline = jest.fn();
    await render(<AiConsentGate onDecline={onDecline}><Protected /></AiConsentGate>);
    fireEvent.press(await screen.findByText("Not now"));
    expect(onDecline).toHaveBeenCalledTimes(1);
    expect(store["ai-consent-v1"]).toBeUndefined();
  });
});
