import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';
import { configureApi } from '../lib/api/client';
import { ApiError } from '../lib/net/errors';
import { UploadError, createForm, uploadFile } from '../lib/media/upload';
import { json } from './helpers';

class FakeForm {
  static last: FakeForm | null = null;
  entries: Array<[string, unknown]> = [];
  constructor() {
    FakeForm.last = this;
  }
  append(name: string, value: unknown) {
    this.entries.push([name, value]);
  }
}

const file = { uri: 'file:///cache/dictation.m4a', name: 'dictation.m4a', mimeType: 'audio/mp4' };

describe('createForm', () => {
  it('streams the file from its place on the phone and adds the other fields', () => {
    const form = createForm(file, { language: 'en' }, FakeForm) as FakeForm;
    assert.deepEqual(form.entries, [
      ['file', { uri: file.uri, name: 'dictation.m4a', type: 'audio/mp4' }],
      ['language', 'en'],
    ]);
  });
});

describe('uploadFile', () => {
  let calls: Array<{ url: string; init: RequestInit }>;
  let answer: () => Response;
  let unauthorized: number;

  beforeEach(() => {
    calls = [];
    unauthorized = 0;
    answer = () => json({ text: 'hello' });
    configureApi({
      baseUrl: 'https://api.test/api/v1',
      getToken: async () => 'tok',
      onUnauthorized: () => void unauthorized++,
      fetchImpl: async (url, init) => {
        calls.push({ url: String(url), init: init ?? {} });
        return answer();
      },
    });
  });

  it('posts the form with the token, and does NOT set a content type (the boundary is added for us)', async () => {
    const result = await uploadFile<{ text: string }>('/dictation/', file, { FormDataImpl: FakeForm });
    assert.deepEqual(result, { text: 'hello' });
    const { url, init } = calls[0];
    assert.equal(url, 'https://api.test/api/v1/dictation/');
    assert.equal(init.method, 'POST');
    const headers = init.headers as Record<string, string>;
    assert.equal(headers.Authorization, 'Bearer tok');
    assert.equal(Object.keys(headers).some((h) => h.toLowerCase() === 'content-type'), false);
    assert.ok(init.body instanceof FakeForm);
  });

  it('turns a refusal code from the server into a plain sentence', async () => {
    answer = () => json({ code: 'heic_not_supported', detail: 'x' }, { status: 415 });
    await assert.rejects(uploadFile('/attachments/', file, { FormDataImpl: FakeForm }), (e: UploadError) => {
      return e instanceof UploadError && e.code === 'heic_not_supported' && /JPEG/.test(e.message) && e.canTryAgain === false;
    });
  });

  it('marks outages as worth retrying', async () => {
    answer = () => json({ code: 'speech_unavailable' }, { status: 503 });
    await assert.rejects(uploadFile('/dictation/', file, { FormDataImpl: FakeForm }), (e: UploadError) => e.canTryAgain === true);
  });

  it('does not retry by itself: a second upload would be a second attachment', async () => {
    answer = () => json({ code: 'speech_unavailable' }, { status: 503 });
    await assert.rejects(uploadFile('/dictation/', file, { FormDataImpl: FakeForm }));
    assert.equal(calls.length, 1);
  });

  it('reports a refused token and passes network failures through untouched', async () => {
    answer = () => json({ detail: 'no' }, { status: 401 });
    await assert.rejects(uploadFile('/attachments/', file, { FormDataImpl: FakeForm }), (e: ApiError) => e.status === 401);
    assert.equal(unauthorized, 1);
  });

  it('gives up on a stalled upload after its deadline', async () => {
    configureApi({
      baseUrl: 'https://api.test',
      getToken: async () => null,
      fetchImpl: (_url, init) => new Promise((_res, rej) => init?.signal?.addEventListener('abort', () => rej(Object.assign(new Error('x'), { name: 'AbortError' })))),
    });
    await assert.rejects(uploadFile('/attachments/', file, { FormDataImpl: FakeForm, timeoutMs: 30 }), (e: ApiError) => e.kind === 'timeout');
  });
});
