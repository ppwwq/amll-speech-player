/** AMLL uses integer milliseconds; HTMLMediaElement uses seconds. */
export function lyricTimeMs(audioSeconds: number, delayMs: number): number {
  return Math.round(audioSeconds * 1000 + delayMs);
}

export function audioTimeSeconds(lineStartMs: number, delayMs: number): number {
  return (lineStartMs - delayMs) / 1000;
}

export function clampSeek(seconds: number, duration: number, range?: [number, number]): number | null {
  if (!Number.isFinite(seconds) || !Number.isFinite(duration) || duration <= 0) return null;
  const min = range ? Math.max(0, Math.min(duration, range[0])) : 0;
  // The end of an A–B range is exclusive. Avoid immediately wrapping on the next tick.
  const max = range ? Math.max(min, Math.min(duration, range[1]) - 0.001) : duration;
  return Math.max(min, Math.min(max, seconds));
}

export class TapGesture {
  private startX = 0;
  private startY = 0;
  private startedAt = 0;
  moved = false;
  begin(x: number, y: number, now: number) {
    this.startX = x; this.startY = y; this.startedAt = now; this.moved = false;
  }
  move(x: number, y: number) {
    this.moved ||= Math.hypot(x - this.startX, y - this.startY) > 10;
  }
  isTap(now: number) { return !this.moved && now - this.startedAt <= 450; }
}

/** A pair must hit the same sentence, within 320ms and 24px. Each pair is consumed once. */
export class DoubleTapGesture {
  private previous: { key: unknown; x: number; y: number; time: number } | null = null;
  accept(key: unknown, x: number, y: number, time: number): boolean {
    const p = this.previous;
    if (p && p.key === key && time - p.time <= 320 && Math.hypot(x - p.x, y - p.y) <= 24) {
      this.previous = null;
      return true;
    }
    this.previous = { key, x, y, time };
    return false;
  }
  reset() { this.previous = null; }
}

/** Drag selection only offers a sentence whose start is playable in the loaded media. */
export function dragSeekTime(lineStartMs: number, delayMs: number, duration: number): number | null {
  if (!Number.isFinite(lineStartMs) || lineStartMs < 0 || !Number.isFinite(delayMs) ||
      !Number.isFinite(duration) || duration <= 0) return null;
  const seconds = audioTimeSeconds(lineStartMs, delayMs);
  return seconds >= 0 && seconds < duration ? seconds : null;
}
