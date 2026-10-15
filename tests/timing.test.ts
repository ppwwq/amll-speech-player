import { test } from 'node:test';
import assert from 'node:assert/strict';
import { audioTimeSeconds, lyricTimeMs, clampSeek, TapGesture, DoubleTapGesture, DOUBLE_TAP_WINDOW_MS, dragSeekTime } from '../src/practice/timing.ts';

test('milliseconds/seconds round trip with positive and negative subtitle offset', () => {
  for (const delay of [-1500, 0, 1250]) for (const start of [0, 1234, 62000, 3600000]) {
    assert.equal(lyricTimeMs(audioTimeSeconds(start, delay), delay), start);
  }
  assert.equal(audioTimeSeconds(12500, 1500), 11);
  assert.equal(lyricTimeMs(1.23456, 0), 1235);
});
test('seek limits, invalid/unloaded media and exclusive A–B end', () => {
  assert.equal(clampSeek(-4, 60), 0);
  assert.equal(clampSeek(70, 60), 60);
  for (const duration of [0, NaN, Infinity]) assert.equal(clampSeek(5, duration), null);
  assert.equal(clampSeek(NaN, 60), null);
  assert.equal(clampSeek(5, 60, [10, 20]), 10);
  assert.equal(clampSeek(20, 60, [10, 20]), 19.999);
});
test('tap tolerance, drag returning to origin, long press', () => {
  const g = new TapGesture();
  g.begin(100, 100, 0); g.move(105, 104); assert.equal(g.isTap(300), true);
  g.move(100, 150); g.move(100, 100); assert.equal(g.isTap(400), false);
  g.begin(0, 0, 0); assert.equal(g.isTap(451), false);
});

test('double tap needs the same sentence, nearby position/time, and consumes exactly one pair', () => {
  const g = new DoubleTapGesture();
  assert.equal(g.accept('line1', 100, 100, 0), false);
  assert.equal(g.accept('line1', 102, 101, 100), true);
  assert.equal(g.accept('line1', 102, 101, 200), false);
  assert.equal(g.accept('line2', 102, 101, 300), false);
  assert.equal(g.accept('line2', 102, 201, 400), false);
  assert.equal(g.accept('line2', 102, 201, 800), false);
  g.reset(); assert.equal(g.accept('line2', 102, 201, 801), false);
});

test('drag candidate must have a finite timestamp playable after offset conversion', () => {
  assert.equal(dragSeekTime(12000, 1250, 60), 10.75);
  assert.equal(dragSeekTime(12000, -1000, 60), 13);
  assert.equal(dragSeekTime(0, 0, 60), 0);
  for (const start of [NaN, Infinity, -1, 60000, 90000]) assert.equal(dragSeekTime(start, 0, 60), null);
  assert.equal(dragSeekTime(0, 1000, 60), null);
  for (const duration of [NaN, Infinity, 0, -1]) assert.equal(dragSeekTime(12000, 0, duration), null);
  assert.equal(dragSeekTime(12000, NaN, 60), null);
});

test('double-tap window boundary and cancellation match delayed single-tap arbitration', () => {
  const g = new DoubleTapGesture();
  g.accept('line', 0, 0, 0);
  assert.equal(g.accept('line', 24, 0, DOUBLE_TAP_WINDOW_MS), true);
  g.accept('line', 0, 0, 1000);
  assert.equal(g.accept('line', 0, 0, 1000 + DOUBLE_TAP_WINDOW_MS + 1), false);
  g.reset();
  assert.equal(g.accept('line', 0, 0, 1400), false);
});
