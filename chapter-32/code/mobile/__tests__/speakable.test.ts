import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { splitForSpeech, toSpeakable } from '../lib/media/speakable';

/** These are the SAME cases as the server's test_speech_text.py: both sides must agree. */
describe('toSpeakable', () => {
  it('does not read markdown marks aloud', () => {
    const md = '## Plan\n\n- **First** item\n- second `item`\n\n1. one\n2. two\n\n> quoted';
    assert.equal(toSpeakable(md), 'Plan\n\nFirst item\nsecond item\n\none\ntwo\n\nquoted');
  });
  it('keeps link labels and turns bare addresses into a phrase', () => {
    assert.equal(toSpeakable('See [the docs](https://example.com/very/long/path?x=1).'), 'See the docs.');
    assert.equal(toSpeakable('Visit https://example.com/a/b now'), 'Visit a link now');
  });
  it('announces code instead of spelling it out', () => {
    const text = toSpeakable("Run this:\n```python\nprint('hi')\n```\nThen stop.");
    assert.match(text, /code omitted/);
    assert.doesNotMatch(text, /print/);
  });
  it('leaves plain text alone', () => {
    assert.equal(toSpeakable('Just a sentence.'), 'Just a sentence.');
  });
});

describe('splitForSpeech', () => {
  it('returns one part for short text and none for empty text', () => {
    assert.deepEqual(splitForSpeech('Hello.', 100), ['Hello.']);
    assert.deepEqual(splitForSpeech('', 100), []);
  });
  it('cuts at sentence ends within the limit and loses nothing', () => {
    const text = Array.from({ length: 200 }, (_, i) => `This is sentence number ${i}.`).join(' ');
    const parts = splitForSpeech(text, 300);
    assert.ok(parts.length > 5);
    assert.ok(parts.every((p) => p.length <= 300 && p.endsWith('.')));
    assert.equal(parts.join(' ').split(/\s+/).join(' '), text.split(/\s+/).join(' '));
  });
  it('still cuts one enormous sentence', () => {
    const parts = splitForSpeech('word '.repeat(500), 100);
    assert.ok(parts.every((p) => p.length <= 100));
    assert.equal(parts.join(' ').split(/\s+/).length, 500);
  });
});
