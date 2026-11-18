import { CameraView, useCameraPermissions } from "expo-camera";
import { useRef, useState } from "react";
import { Linking, Pressable, Text, View } from "react-native";

import { Button } from "../ui";
import type { PickedAsset } from "./mediaRules";

/** A full-screen camera. Use it when the system camera screen is not enough. */
export function CameraCapture(props: { onCapture: (asset: PickedAsset) => void; onClose: () => void }) {
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);
  const [taking, setTaking] = useState(false);

  if (!permission) return <View style={{ flex: 1, backgroundColor: "#000" }} />; // still checking

  if (!permission.granted) {
    return (
      <View style={{ flex: 1, justifyContent: "center", padding: 24, backgroundColor: "#fff" }}>
        <Text style={{ fontSize: 16, marginBottom: 16 }}>
          We use the camera only to photograph documents you choose to upload.
        </Text>
        {permission.canAskAgain ? (
          <Button title="Allow camera" onPress={() => void requestPermission()} />
        ) : (
          <Button title="Open Settings" onPress={() => void Linking.openSettings()} />
        )}
        <Button title="Not now" kind="plain" onPress={props.onClose} />
      </View>
    );
  }

  async function shoot() {
    if (taking) return;
    setTaking(true);
    try {
      const photo = await camera.current?.takePictureAsync({ quality: 0.7 });
      if (photo) props.onCapture({ uri: photo.uri, width: photo.width, height: photo.height, mimeType: "image/jpeg" });
    } finally {
      setTaking(false);
    }
  }

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }}>
      <CameraView ref={camera} style={{ flex: 1 }} facing="back" />
      <View style={{ flexDirection: "row", justifyContent: "space-around", alignItems: "center", padding: 24 }}>
        <Pressable onPress={props.onClose} accessibilityRole="button"><Text style={{ color: "#fff", fontSize: 16 }}>Cancel</Text></Pressable>
        <Pressable onPress={shoot} accessibilityRole="button" accessibilityLabel="Take photo"
          style={{ width: 72, height: 72, borderRadius: 36, backgroundColor: "#fff", opacity: taking ? 0.5 : 1 }} />
        <View style={{ width: 48 }} />
      </View>
    </View>
  );
}
