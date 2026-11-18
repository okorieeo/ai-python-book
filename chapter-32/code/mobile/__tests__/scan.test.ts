import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { parseScannedUrl } from '../lib/cv/scan';

const HOSTS = ['example.com'];
const ok = (s: string) => parseScannedUrl(s, HOSTS).ok;

describe('parseScannedUrl', () => {
  it('accepts https addresses on an allowed host or one of its subdomains', () => {
    assert.equal(ok('https://example.com/invite/abc'), true);
    assert.equal(ok('https://app.example.com/join?code=1#x'), true);
    assert.equal(ok('HTTPS://EXAMPLE.COM'), true);
    assert.equal(ok('https://example.com:443/x'), true);
  });

  it('refuses other schemes: http, javascript, file, intent, tel, sms and plain text', () => {
    for (const bad of ['http://example.com', 'javascript:alert(1)', 'file:///etc/passwd', 'intent://scan#Intent;end', 'tel:+123', 'sms:+123', 'just text', 'WIFI:S:net;P:pass;;']) {
      assert.equal(ok(bad), false, bad);
    }
  });

  it('refuses look-alike and tricky hosts', () => {
    for (const bad of [
      'https://example.com.evil.net/x', 'https://notexample.com/x', 'https://evil.net/https://example.com',
      'https://example.com@evil.net/x', 'https://user:pass@example.com/x', 'https://example.com:8443/x',
      'https://evil.net#@example.com', 'https://127.0.0.1/x', 'https://localhost/x', 'https://exämple.com/x',
    ]) {
      assert.equal(ok(bad), false, bad);
    }
  });

  it('refuses control characters, spaces and absurd length', () => {
    assert.equal(ok('https://example.com/a b'), false);
    assert.equal(ok('https://example.com/a\nb'), false);
    assert.equal(ok('https://example.com/' + 'a'.repeat(3000)), false);
    assert.equal(ok(''), false);
  });

  it('explains a refusal', () => {
    const result = parseScannedUrl('http://example.com', HOSTS);
    assert.deepEqual(result, { ok: false, reason: 'not an https address' });
  });
});
