import { getApiConfig } from '../api/client';
import { ApiError, isUnauthorized } from '../net/errors';
import { requestJson } from '../net/fetchWithTimeout';
import { canTryAgain, messageForCode } from './uploadMessages';

export interface LocalFile {
  uri: string;
  name: string;
  mimeType: string;
}

/** A refusal from the server, with the words to show. `code` is the server's reason. */
export class UploadError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly canTryAgain: boolean,
  ) {
    super(message);
    this.name = 'UploadError';
  }
}

interface FormLike {
  append(name: string, value: unknown): void;
}

/**
 * React Native's FormData accepts { uri, name, type } for a file on the phone and hands the file to the
 * native networking layer, instead of reading it into JavaScript memory. (Browsers want a Blob instead; that is why
 * the constructor is injectable: the tests pass a fake.)
 */
export function createForm(
  file: LocalFile,
  fields: Record<string, string> = {},
  FormDataImpl: new () => FormLike = FormData as unknown as new () => FormLike,
): FormLike {
  const form = new FormDataImpl();
  form.append('file', { uri: file.uri, name: file.name, type: file.mimeType });
  for (const [name, value] of Object.entries(fields)) form.append(name, value);
  return form;
}

export interface UploadOptions<T> {
  fields?: Record<string, string>;
  /** Default 60 s: uploads are slower than ordinary calls. */
  timeoutMs?: number;
  signal?: AbortSignal | null;
  parse?: (data: unknown) => T;
  FormDataImpl?: new () => FormLike;
}

/**
 * POST a file as multipart/form-data.
 * - never sets Content-Type by hand: the multipart boundary is added automatically, and setting it breaks the upload
 * - is NOT retried automatically: a repeated upload is a second attachment. The user taps "Try again".
 * - turns the server's refusal codes into a plain sentence
 */
export async function uploadFile<T = unknown>(path: string, file: LocalFile, options: UploadOptions<T> = {}): Promise<T> {
  const { baseUrl, getToken, onUnauthorized, fetchImpl } = getApiConfig();
  const token = await getToken();
  try {
    return await requestJson<T>(`${baseUrl}${path}`, {
      method: 'POST',
      body: createForm(file, options.fields, options.FormDataImpl) as unknown as FormData,
      headers: { Accept: 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      timeoutMs: options.timeoutMs ?? 60_000,
      signal: options.signal,
      parse: options.parse,
      fetchImpl,
    });
  } catch (error) {
    if (isUnauthorized(error)) onUnauthorized?.();
    const code = error instanceof ApiError && error.kind === 'http' ? (error.body as { code?: unknown } | undefined)?.code : undefined;
    if (typeof code === 'string') throw new UploadError(code, messageForCode(code), canTryAgain(code));
    throw error; // network, timeout and the rest: the screen shows userMessage(error)
  }
}
