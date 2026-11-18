import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import { MEDIA_LIMITS } from '../lib/media/limits';
import { prepareImage } from '../lib/media/prepareImage';
import type { LocalFile } from '../lib/media/upload';

interface Props {
  onFile: (file: LocalFile) => void;
  disabled?: boolean;
}

/** Three ways to add a file. Each one prepares the file on the phone and hands it to `onFile`. */
export function AttachmentPicker({ onFile, disabled }: Props) {
  const fromLibrary = async () => {
    // On current versions of both systems the system photo picker usually needs no permission prompt.
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 1, exif: false });
    if (result.canceled || !result.assets[0]) return;
    onFile(await prepareImage(result.assets[0]));
  };

  const fromCamera = async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) return Alert.alert('Camera access is off', 'You can allow it in Settings.');
    const result = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 1, exif: false });
    if (result.canceled || !result.assets[0]) return;
    onFile(await prepareImage(result.assets[0]));
  };

  const fromFiles = async () => {
    const result = await DocumentPicker.getDocumentAsync({ type: 'application/pdf', copyToCacheDirectory: true });
    const asset = result.canceled ? undefined : result.assets[0];
    if (!asset) return;
    if (asset.size && asset.size > MEDIA_LIMITS.maxPdfBytes) return Alert.alert('That PDF is too large', 'Choose a smaller file or fewer pages.');
    onFile({ uri: asset.uri, name: asset.name, mimeType: 'application/pdf' });
  };

  return (
    <View style={styles.row} accessibilityRole="toolbar">
      {[
        ['Photo', fromLibrary],
        ['Camera', fromCamera],
        ['PDF', fromFiles],
      ].map(([label, handler]) => (
        <Pressable key={label as string} accessibilityRole="button" accessibilityLabel={`Attach ${String(label)}`} disabled={disabled} onPress={() => void (handler as () => Promise<void>)()} style={[styles.button, disabled && styles.disabled]}>
          <Text style={styles.text}>{label as string}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 8, padding: 8 },
  button: { minHeight: 44, minWidth: 72, alignItems: 'center', justifyContent: 'center', borderRadius: 12, borderWidth: 1, borderColor: '#D1D5DB', paddingHorizontal: 12 },
  disabled: { opacity: 0.4 },
  text: { fontWeight: '600', color: '#1D4ED8' },
});
