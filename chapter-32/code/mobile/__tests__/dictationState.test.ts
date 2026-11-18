import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { dictationReducer, initialDictation, type DictationEvent, type DictationState } from '../lib/media/dictationState';

const run = (events: DictationEvent[], start: DictationState = initialDictation, max?: number) =>
  events.reduce((state, event) => dictationReducer(state, event, max), start);

describe('dictation state machine', () => {
  it('goes from idle through recording and uploading back to idle with the text', () => {
    const state = run([{ type: 'press' }, { type: 'permission', granted: true }, { type: 'tick' }, { type: 'tick' }, { type: 'stop' }, { type: 'uploaded', text: 'hello' }]);
    assert.deepEqual(state, { phase: 'idle', seconds: 0, text: 'hello' });
  });

  it('pressing the button again while recording also stops', () => {
    assert.equal(run([{ type: 'press' }, { type: 'permission', granted: true }, { type: 'press' }]).phase, 'uploading');
  });

  it('a denied microphone ends in an error that points to Settings', () => {
    const state = run([{ type: 'press' }, { type: 'permission', granted: false }]);
    assert.equal(state.phase, 'error');
    assert.equal(state.error?.needsSettings, true);
    assert.equal(state.error?.canTryAgain, false);
  });

  it('stops by itself at the time limit', () => {
    const state = run([{ type: 'press' }, { type: 'permission', granted: true }, ...Array(3).fill({ type: 'tick' })], initialDictation, 3);
    assert.equal(state.phase, 'uploading');
    assert.equal(state.seconds, 3);
  });

  it('cancelling while recording uploads nothing', () => {
    const state = run([{ type: 'press' }, { type: 'permission', granted: true }, { type: 'tick' }, { type: 'cancel' }]);
    assert.deepEqual(state, initialDictation);
  });

  it('ignores events that make no sense in the current state', () => {
    assert.deepEqual(run([{ type: 'tick' }, { type: 'stop' }, { type: 'uploaded', text: 'x' }]), initialDictation);
    const uploading = run([{ type: 'press' }, { type: 'permission', granted: true }, { type: 'stop' }]);
    assert.deepEqual(run([{ type: 'press' }, { type: 'tick' }], uploading), uploading); // no second recording while uploading
  });

  it('a late answer after cancelling is ignored', () => {
    const state = run([{ type: 'press' }, { type: 'permission', granted: true }, { type: 'stop' }, { type: 'cancel' }, { type: 'uploaded', text: 'late' }]);
    assert.deepEqual(state, initialDictation);
  });

  it('an upload failure can be retried by pressing the button again', () => {
    const failed = run([{ type: 'press' }, { type: 'permission', granted: true }, { type: 'stop' }, { type: 'failed', message: 'Busy', canTryAgain: true }]);
    assert.equal(failed.error?.canTryAgain, true);
    assert.equal(dictationReducer(failed, { type: 'press' }).phase, 'asking');
  });
});
