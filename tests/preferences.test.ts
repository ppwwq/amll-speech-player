import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PreferenceMemory, PREFERENCE_DEFAULTS, PREFERENCES_KEY, LEGACY_SETTINGS_KEY, LEGACY_DRAG_KEY,
  sanitizePreferences, validControlPointCode, type PreferenceStatus } from '../src/practice/preferences.ts';

function fixture() {
  const data = new Map<string, string>();
  const reports: PreferenceStatus[] = [];
  let fail = false, writes = 0;
  const storage = { getItem: (k: string) => data.get(k) ?? null, removeItem: (k: string) => { data.delete(k); },
    setItem: (k: string, v: string) => { if (fail) throw new Error('QuotaExceeded'); writes++; data.set(k, v); } };
  const memory = new PreferenceMemory(() => storage, s => reports.push(s));
  return { data, reports, storage, memory, writes: () => writes, fail: (value: boolean) => { fail = value; } };
}

test('preference round trip retains zero/false and serializes only preferences', () => {
  const f = fixture();
  const values = { ...PREFERENCE_DEFAULTS, volume: 0, backgroundFlowSpeed: 0, loopPlay: false,
    dragSeekEnabled: false, showRomanLyric: false, musicUrl: 'private', currentTime: 12, isPlaying: true, autoPlay: true };
  assert.equal(f.memory.save(values), true);
  const restored = f.memory.read();
  assert.deepEqual(restored, sanitizePreferences(values).values);
  for (const key of ['musicUrl', 'currentTime', 'isPlaying', 'autoPlay']) assert.equal(Object.hasOwn(restored, key), false);
  assert.equal(restored.volume, 0); assert.equal(restored.backgroundFlowSpeed, 0);
  assert.equal(restored.loopPlay, false); assert.equal(restored.dragSeekEnabled, false);
});

test('legacy records migrate without writing defaults during read', () => {
  const f = fixture();
  f.data.set(LEGACY_SETTINGS_KEY, JSON.stringify({ backgroundFlowSpeed: 0, showTranslatedLyric: false, backgroundRenderScale: 0.5 }));
  f.data.set(LEGACY_DRAG_KEY, 'false');
  assert.deepEqual(f.memory.read(), { backgroundFlowSpeed: 0, backgroundRenderScale: 0.5, showTranslatedLyric: false, dragSeekEnabled: false });
  assert.equal(f.writes(), 0); assert.equal(f.data.has(PREFERENCES_KEY), false);
  f.memory.save({ ...PREFERENCE_DEFAULTS, ...f.memory.read(), volume: 0.3 });
  assert.equal(f.memory.read().volume, 0.3);
  assert.equal(f.memory.read().dragSeekEnabled, false);
});

test('malformed fields cannot enter state; valid fields survive independently', () => {
  const bad = { playbackRate: Infinity, volume: -1, backgroundFPS: 1e9, enableLyricSpring: 'false',
    backgroundType: 'invalid', lyricAlignAnchor: 'middle', manualDominantColor: 'url(secret)',
    backgroundMaskColor: null, backgroundFlowSpeed: '0', roundedCover: 101, fftDataRangeMin: 200, fftDataRangeMax: 100,
    loopPlay: false, showRemainingTime: true };
  assert.deepEqual(sanitizePreferences(bad), { values: { loopPlay: false, showRemainingTime: true }, invalid: true });
  for (const raw of [null, true, [], 4, 'text']) assert.equal(sanitizePreferences(raw).invalid, true);
  assert.deepEqual(sanitizePreferences(Object.create({ volume: 0.2 })).values, {});
});

test('corrupt JSON and old data fail safely, then recover on a valid change', () => {
  for (const text of ['{bad', 'null', '[]', '{"version":"bad"}']) {
    const f = fixture(); f.data.set(PREFERENCES_KEY, text);
    assert.deepEqual(f.memory.read(), {}); assert.equal(f.reports.at(-1)?.phase, 'error');
    assert.equal(f.writes(), 0); assert.equal(f.memory.save(PREFERENCE_DEFAULTS), true);
  }
  const f = fixture(); f.data.set(LEGACY_SETTINGS_KEY, '{bad'); f.data.set(LEGACY_DRAG_KEY, 'false');
  assert.equal(f.memory.read().dragSeekEnabled, false); assert.equal(f.reports.at(-1)?.phase, 'error');
});

test('future schema is preserved instead of overwritten by an older application', () => {
  const f = fixture(), original = '{"version":2,"values":{"volume":0.1}}';
  f.data.set(PREFERENCES_KEY, original); assert.deepEqual(f.memory.read(), {});
  assert.equal(f.memory.save(PREFERENCE_DEFAULTS), false);
  assert.equal(f.data.get(PREFERENCES_KEY), original); assert.equal(f.writes(), 0);
});

test('blocked storage and write failure do not throw or claim saved; next change retries', () => {
  const reports: PreferenceStatus[] = [];
  const blocked = new PreferenceMemory(() => { throw new Error('SecurityError'); }, s => reports.push(s));
  assert.deepEqual(blocked.read(), {}); assert.equal(blocked.save(PREFERENCE_DEFAULTS), false);
  assert.ok(reports.every(s => s.phase === 'error'));
  const f = fixture(); f.memory.save(PREFERENCE_DEFAULTS); const previous = f.data.get(PREFERENCES_KEY);
  f.fail(true); assert.equal(f.memory.save({ ...PREFERENCE_DEFAULTS, volume: 0.1 }), false);
  assert.equal(f.data.get(PREFERENCES_KEY), previous); assert.equal(f.reports.at(-1)?.phase, 'error');
  f.fail(false); assert.equal(f.memory.save({ ...PREFERENCE_DEFAULTS, volume: 0.1 }), true);
  assert.equal(f.memory.read().volume, 0.1);
});

test('stored mesh configurations accept the existing JSON formats within finite bounds', () => {
  const points = [[0,0,-1,-1,0,0,1,1],[1,1,1,1,0,0,1,1]];
  for (const data of [{width:2,height:2,conf:points},[2,2,...points],points]) {
    assert.notEqual(validControlPointCode(JSON.stringify(data)), null);
  }
  for (const data of [{width:1e8,height:2,conf:points},{width:2,height:2,conf:[[3,0,0,0,0,0,1,1]]},
    [2,2,[0,0,'bad',0,0,0,1,1]],{},[],null]) assert.equal(validControlPointCode(JSON.stringify(data)), null);
  assert.equal(validControlPointCode(''), ''); assert.equal(validControlPointCode('alert(1)'), null);
});
