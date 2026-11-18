import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { createDraftStore, MAX_DRAFT_LENGTH } from '../lib/offline/drafts';
import { MemoryStorage } from '../lib/offline/storage';

describe('draft store', () => {
  it('keeps unsent text per conversation', async () => {
    const drafts = createDraftStore(new MemoryStorage());
    await drafts.set('c1', 'half a thought');
    assert.equal(await drafts.get('c1'), 'half a thought');
    assert.equal(await drafts.get('c2'), null);
  });

  it('forgets a draft that was emptied, and caps absurdly long ones', async () => {
    const storage = new MemoryStorage();
    const drafts = createDraftStore(storage);
    await drafts.set('c1', 'x');
    await drafts.set('c1', '   ');
    assert.equal(await drafts.get('c1'), null);
    await drafts.set('c1', 'y'.repeat(MAX_DRAFT_LENGTH + 500));
    assert.equal((await drafts.get('c1'))!.length, MAX_DRAFT_LENGTH);
  });

  it('clearAll() removes drafts and nothing else (sign-out)', async () => {
    const storage = new MemoryStorage();
    await storage.setItem('settings:theme', 'dark');
    const drafts = createDraftStore(storage);
    await drafts.set('c1', 'a');
    await drafts.set('c2', 'b');
    await drafts.clearAll();
    assert.deepEqual([...storage.data.keys()], ['settings:theme']);
  });
});
