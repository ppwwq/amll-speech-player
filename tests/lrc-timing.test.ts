import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeLrcTimings } from '../src/lyric/lrc-timing.ts';

const line = (start: number, end: number, text: string) => ({
  startTime: start, endTime: end, words: [{ word: text, startTime: start, endTime: end }],
  translatedLyric: '', romanLyric: '', isBG: false, isDuet: false,
});

test('plain LRC sorts before inferring intervals and retains simultaneous rows', () => {
  const input = [line(9000,3000,'Nine'),line(3000,3000,'A'),line(3000,0,'B'),line(0,6000,'Zero'),line(6000,11000,'Six')];
  const before = structuredClone(input);
  const result = normalizeLrcTimings(input);
  assert.deepEqual(result.map(l=>[l.startTime,l.endTime,l.words[0].word]), [
    [0,3000,'Zero'],[3000,6000,'A'],[3000,6000,'B'],[6000,9000,'Six'],[9000,14000,'Nine'],
  ]);
  assert.deepEqual(result.map(l=>l.words[0].endTime),result.map(l=>l.endTime));
  assert.deepEqual(input,before);
});

test('empty, single and duplicate final timestamps have finite positive intervals', () => {
  assert.deepEqual(normalizeLrcTimings([]),[]);
  assert.equal(normalizeLrcTimings([line(1234,0,'Only')])[0].endTime,6234);
  assert.deepEqual(normalizeLrcTimings([line(1234,1234,'A'),line(1234,6234,'B')]).map(l=>l.endTime),[6234,6234]);
});

test('plain and repeated-timestamp LRC must not be misrouted to SPL', async () => {
  const { isSPLFormat, isLyRiCA2Format, isWalaokeFormat } = await import('../src/lyric/lyric-parsers.ts');
  assert.equal(isSPLFormat('[00:09.00]Nine\n[00:03.00]Three'),false);
  assert.equal(isSPLFormat('[00:06.00][00:12.00]Repeat'),false);
  assert.equal(isSPLFormat('[00:06.00]Hello<00:07.00> world<00:08.00>'),true);
  assert.equal(isLyRiCA2Format('[00:06.000]<00:06.000>Hello<00:07.000>'),true);
  assert.equal(isWalaokeFormat('[00:06.000]v1: Hello'),true);
});
