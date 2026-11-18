/**
 * Every refusal code the server can send (Chapter 32 backend), in plain words.
 * The server sends a short `code`; the words live here so the app can be translated and reworded
 * without touching the server.
 */
const MESSAGES: Record<string, string> = {
  no_file: 'Nothing was attached. Please try again.',
  file_too_large: 'That file is too large. Try a smaller one.',
  unsupported_type: 'That type of file is not supported. You can share pictures, PDFs and voice recordings.',
  heic_not_supported: 'That photo is in a format we cannot read yet. Please share it as a JPEG.',
  daily_upload_limit: 'You have reached today\'s upload limit. Please try again tomorrow.',
  storage_quota_exceeded: 'Your storage is full. Delete some files and try again.',
  unreadable_image: 'We could not read that picture. It may be damaged.',
  image_too_many_pixels: 'That picture is enormous. Please share a smaller version.',
  image_too_complex: 'That picture is too detailed to send. Please share a smaller version.',
  unreadable_pdf: 'We could not read that PDF. It may be damaged.',
  pdf_encrypted: 'That PDF is password protected. Remove the password and try again.',
  pdf_too_many_pages: 'That PDF has too many pages. Share a shorter one or only the pages you need.',
  bad_page_range: 'Those page numbers do not exist in this PDF.',
  unreadable_audio: 'We could not read that recording.',
  audio_too_long: 'That recording is too long.',
  audio_processing_timeout: 'That recording took too long to process. Try a shorter one.',
  no_speech_found: 'We did not hear any speech. Try again, a little closer to the microphone.',
  speech_unavailable: 'Speech recognition is busy right now. Please try again in a moment.',
  provider_rejected: 'The speech service could not use that recording.',
  provider_config: 'This feature is not available right now. Please try again later.',
  provider_unavailable: 'This feature is busy right now. Please try again in a moment.',
  internal_error: 'Something went wrong on our side. Please try again.',
  too_many_attachments: 'You can attach up to 5 files to one message.',
  attachment_not_found: 'One of the files is no longer available. Please attach it again.',
  attachment_not_ready: 'A file is still being prepared. Please wait a moment.',
  nothing_to_say: 'There is nothing to read aloud in this message.',
  bad_part: 'That part of the message does not exist.',
};

export const KNOWN_CODES = Object.keys(MESSAGES);

const GENERIC = 'That did not work. Please try again.';

export function messageForCode(code: unknown): string {
  return typeof code === 'string' && code in MESSAGES ? MESSAGES[code] : GENERIC;
}

/** Codes where trying the same thing again a little later can succeed. */
const RETRY_LATER = new Set(['speech_unavailable', 'provider_unavailable', 'audio_processing_timeout', 'internal_error']);

export const canTryAgain = (code: unknown): boolean => typeof code === 'string' && RETRY_LATER.has(code);
