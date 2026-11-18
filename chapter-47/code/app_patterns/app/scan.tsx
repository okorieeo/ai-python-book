import { CameraView, useCameraPermissions } from "expo-camera";
import { useRef, useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

export default function Scan() {
  const [permission, requestPermission] = useCameraPermissions();
  const scanned = useRef(false);
  const [result, setResult] = useState<string | null>(null);

  if (!permission) return null; // still checking
  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.text}>We use the camera only to scan codes. Nothing is saved or uploaded.</Text>
        {permission.canAskAgain ? (
          <Pressable accessibilityRole="button" onPress={requestPermission} style={styles.button}>
            <Text style={styles.buttonText}>Allow camera</Text>
          </Pressable>
        ) : (
          // The system will not show the prompt again: the only way is the Settings app.
          <Pressable accessibilityRole="button" onPress={() => Linking.openSettings()} style={styles.button}>
            <Text style={styles.buttonText}>Open Settings</Text>
          </Pressable>
        )}
      </View>
    );
  }

  return (
    <View style={styles.fill}>
      <CameraView
        style={styles.fill}
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
        onBarcodeScanned={({ data }) => {
          if (scanned.current) return; // the scanner fires many times per second
          scanned.current = true;
          setResult(data);
        }}
      />
      {result ? <Text style={styles.result}>{result}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  center: { flex: 1, justifyContent: "center", padding: 24, gap: 16 },
  text: { fontSize: 16 },
  button: { backgroundColor: "#1e3a8a", borderRadius: 8, padding: 14, alignItems: "center" },
  buttonText: { color: "#fff", fontWeight: "600" },
  result: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: "#fff", padding: 12 },
});
