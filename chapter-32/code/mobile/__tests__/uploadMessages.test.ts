import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { KNOWN_CODES, canTryAgain, messageForCode } from '../lib/media/uploadMessages';

/** The codes the Django views and services can send (attachments/*.py). If the server gains a code, add it here. */
const SERVER_CODES = [
  'no_file', 'file_too_large', 'unsupported_type', 'heic_not_supported', 'daily_upload_limit', 'storage_quota_exceeded',
  'unreadable_image', 'image_too_many_pixels', 'image_too_complex', 'unreadable_pdf', 'pdf_encrypted', 'pdf_too_many_pages',
  'bad_page_range', 'unreadable_audio', 'audio_too_long', 'audio_processing_timeout', 'no_speech_found', 'speech_unavailable',
  'provider_rejected', 'provider_config', 'provider_unavailable', 'internal_error', 'too_many_attachments',
  'attachment_not_found', 'attachment_not_ready', 'nothing_to_say', 'bad_part',
];

describe('messageForCode', () => {
  it('has wording for every code the server can send', () => {
    for (const code of SERVER_CODES) assert.ok(KNOWN_CODES.includes(code), `missing: ${code}`);
  });

  it('never shows a raw code or technical word to the user', () => {
    for (const code of KNOWN_CODES) assert.doesNotMatch(messageForCode(code), /_|[0-9]{3}|undefined|null|exception/i, code);
  });

  it('falls back to a calm generic sentence for anything unknown', () => {
    for (const unknown of ['brand_new_code', undefined, 42, null]) assert.match(messageForCode(unknown), /try again/i);
  });

  it('offers "try again" only where trying again can help', () => {
    assert.equal(canTryAgain('speech_unavailable'), true);
    assert.equal(canTryAgain('file_too_large'), false);
    assert.equal(canTryAgain(undefined), false);
  });
});
