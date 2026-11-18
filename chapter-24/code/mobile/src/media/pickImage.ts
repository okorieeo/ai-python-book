import * as ImagePicker from "expo-image-picker";

import { toFormData, validateAsset, type PickedAsset } from "./mediaRules";
import { ensurePermission, type PermissionOutcome } from "./permissions";

export type PickResult =
  | { kind: "picked"; asset: PickedAsset; form: FormData }
  | { kind: "cancelled" }
  | { kind: "invalid"; message: string }
  | { kind: "permission"; outcome: Exclude<PermissionOutcome, "granted"> };

function finish(result: ImagePicker.ImagePickerResult): PickResult {
  if (result.canceled || result.assets.length === 0) return { kind: "cancelled" };
  const asset = result.assets[0];
  const verdict = validateAsset(asset);
  if (!verdict.ok) return { kind: "invalid", message: verdict.message };
  return { kind: "picked", asset, form: toFormData(asset) };
}

// quality below 1 makes the picker re-encode the photo as a smaller JPEG.
const options = { mediaTypes: ["images" as const], quality: 0.8 };

export async function choosePhoto(square = false): Promise<PickResult> {
  // The system photo picker shows only what the person selects: no permission needed.
  return finish(
    await ImagePicker.launchImageLibraryAsync({
      ...options,
      allowsEditing: square,
      aspect: square ? [1, 1] : undefined,
    }),
  );
}

export async function takePhoto(square = false): Promise<PickResult> {
  const outcome = await ensurePermission(
    ImagePicker.getCameraPermissionsAsync,
    ImagePicker.requestCameraPermissionsAsync,
  );
  if (outcome !== "granted") return { kind: "permission", outcome };
  return finish(
    await ImagePicker.launchCameraAsync({
      ...options,
      allowsEditing: square,
      aspect: square ? [1, 1] : undefined,
    }),
  );
}
