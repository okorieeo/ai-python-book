// What the SERVER accepts (Chapter 16), checked on the phone first so the person
// finds out in a quarter of a second, not after a 9 MB upload over a bad network.
// The server still checks everything again. This is politeness, not security.

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // UPLOAD_MAX_BYTES in settings.py
export const PHOTO_TYPES = ["image/jpeg", "image/png"];

export interface PickedAsset {
  uri: string;
  mimeType?: string | null;
  fileName?: string | null;
  fileSize?: number | null;
  width?: number;
  height?: number;
}

export type Verdict = { ok: true } | { ok: false; message: string };

const BY_EXTENSION: Record<string, string> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  heic: "image/heic",
  heif: "image/heif",
};

/** Some pickers leave mimeType empty. Fall back to the file extension. */
export function mimeTypeOf(asset: PickedAsset): string {
  if (asset.mimeType) return asset.mimeType.toLowerCase();
  const ext = (asset.fileName ?? asset.uri).split("?")[0].split(".").pop()?.toLowerCase() ?? "";
  return BY_EXTENSION[ext] ?? "application/octet-stream";
}

export function validateAsset(asset: PickedAsset): Verdict {
  const type = mimeTypeOf(asset);
  if (type === "image/heic" || type === "image/heif") {
    return { ok: false, message: "This photo is in HEIC format. Choose a JPEG or PNG." };
  }
  if (!PHOTO_TYPES.includes(type)) {
    return { ok: false, message: "Only JPEG and PNG photos can be uploaded." };
  }
  if (asset.fileSize === 0) return { ok: false, message: "That file is empty." };
  if (asset.fileSize != null && asset.fileSize > MAX_UPLOAD_BYTES) {
    const mb = (asset.fileSize / (1024 * 1024)).toFixed(1);
    return { ok: false, message: `That photo is ${mb} MB. The limit is 10 MB.` };
  }
  return { ok: true };
}

/** A filename for display only. The server ignores it when it builds the storage key. */
export function displayName(asset: PickedAsset, fallback = "photo"): string {
  const type = mimeTypeOf(asset);
  const ext = type === "image/png" ? "png" : "jpg";
  const given = asset.fileName?.trim();
  return given ? given : `${fallback}-${Date.now()}.${ext}`;
}

/**
 * React Native lets FormData carry a file as a plain object {uri, name, type}.
 * The browser FormData you know from Chapter 20 does not: it needs a Blob.
 */
export function toFormData(
  asset: PickedAsset,
  FormDataClass: typeof FormData = FormData,
  field = "file",
): FormData {
  const form = new FormDataClass();
  form.append(field, {
    uri: asset.uri,
    name: displayName(asset),
    type: mimeTypeOf(asset),
  } as unknown as Blob);
  return form;
}
