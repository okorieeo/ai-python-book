import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import { useMemo, useRef } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { StableDetector } from '../lib/cv/geometry';
import { parseScannedUrl } from '../lib/cv/scan';

interface Props {
  allowedHosts: string[];
  onUrl: (url: string) => void;
  onRejected?: (reason: string) => void;
}

/** Scans QR codes and reports only web addresses that pass `parseScannedUrl`. */
export function QrScanner({ allowedHosts, onUrl, onRejected }: Props) {
  const [permission, requestPermission] = useCameraPermissions();
  const detector = useRef(new StableDetector({ framesRequired: 3, cooldownMs: 4000 })).current;
  const seenAny = useRef(false);

  const handle = useMemo(
    () => (result: BarcodeScanningResult) => {
      seenAny.current = true;
      const stable = detector.update(result.data, Date.now()); // act only when the same code is seen in 3 frames
      if (stable === null) return;
      const parsed = parseScannedUrl(stable, allowedHosts);
      if (parsed.ok) onUrl(parsed.url);
      else onRejected?.(parsed.reason);
    },
    [allowedHosts, detector, onRejected, onUrl],
  );

  if (!permission) return <View style={styles.fill} />;
  if (!permission.granted) {
    return (
      <View style={[styles.fill, styles.center]}>
        <Text style={styles.message}>We need the camera to scan codes.</Text>
        <Pressable accessibilityRole="button" onPress={() => void requestPermission()} style={styles.button}>
          <Text style={styles.buttonText}>Allow camera</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <CameraView
      style={styles.fill}
      facing="back"
      barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
      onBarcodeScanned={handle}
      accessibilityLabel="Camera view for scanning a QR code"
    />
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  center: { alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 },
  message: { fontSize: 16, textAlign: 'center' },
  button: { minHeight: 44, paddingHorizontal: 20, borderRadius: 12, backgroundColor: '#1D4ED8', alignItems: 'center', justifyContent: 'center' },
  buttonText: { color: '#FFFFFF', fontWeight: '600' },
});
