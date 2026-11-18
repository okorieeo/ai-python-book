import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { connectionQuality, isOnline, shouldDeferLargeTransfers, type NetState } from '../lib/net/connectivity';

const state = (isConnected: boolean | null, isInternetReachable: boolean | null, extra: Partial<NetState> = {}): NetState => ({
  isConnected,
  isInternetReachable,
  ...extra,
});

describe('isOnline', () => {
  it('is offline only when we know it', () => {
    assert.equal(isOnline(state(true, true)), true);
    assert.equal(isOnline(state(true, null)), true); // reachability not measured yet
    assert.equal(isOnline(state(null, null)), true); // unknown at startup: try, do not flash a banner
    assert.equal(isOnline(state(false, false)), false);
  });

  it('treats Wi-Fi without internet (captive portal, dead router) as offline', () => {
    assert.equal(isOnline(state(true, false, { type: 'wifi' })), false);
  });
});

describe('connectionQuality', () => {
  it('flags 2G and 3G as poor, everything else as good', () => {
    assert.equal(connectionQuality(state(true, true, { type: 'cellular', details: { cellularGeneration: '3g' } })), 'poor');
    assert.equal(connectionQuality(state(true, true, { type: 'cellular', details: { cellularGeneration: '2g' } })), 'poor');
    assert.equal(connectionQuality(state(true, true, { type: 'cellular', details: { cellularGeneration: '4g' } })), 'good');
    assert.equal(connectionQuality(state(true, true, { type: 'wifi' })), 'good');
  });

  it('reports offline and unknown', () => {
    assert.equal(connectionQuality(state(false, false)), 'offline');
    assert.equal(connectionQuality(state(null, null)), 'unknown');
  });
});

describe('shouldDeferLargeTransfers', () => {
  it('holds back big transfers on poor, offline or metered connections', () => {
    assert.equal(shouldDeferLargeTransfers(state(true, true, { type: 'wifi' })), false);
    assert.equal(shouldDeferLargeTransfers(state(true, true, { type: 'cellular', details: { cellularGeneration: '3g' } })), true);
    assert.equal(shouldDeferLargeTransfers(state(true, true, { type: 'cellular', details: { cellularGeneration: '4g', isConnectionExpensive: true } })), true);
    assert.equal(shouldDeferLargeTransfers(state(false, false)), true);
  });
});
