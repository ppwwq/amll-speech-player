import type { LyricLine } from '@applemusic-like-lyrics/lyric';

/** Plain LRC has starts only: infer ends AFTER sorting, sharing an interval
 * across simultaneous rows. Keep the existing player's five-second final tail.
 * Do not apply this to word-timed formats, which have explicit end times.
 */
export function normalizeLrcTimings(lines: LyricLine[]): LyricLine[] {
  const sorted = lines.map(line => ({ ...line, words: line.words.map(word => ({ ...word })) }))
    .sort((a, b) => a.words[0].startTime - b.words[0].startTime);
  let nextStart = 0;
  for (let i = sorted.length - 1; i >= 0; i--) {
    const start = sorted[i].words[0].startTime;
    if (i === sorted.length - 1) nextStart = start + 5000;
    else if (sorted[i + 1].words[0].startTime > start) nextStart = sorted[i + 1].words[0].startTime;
    sorted[i].startTime = start;
    sorted[i].endTime = nextStart;
    sorted[i].words[sorted[i].words.length - 1].endTime = nextStart;
  }
  return sorted;
}
