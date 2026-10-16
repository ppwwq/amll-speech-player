import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decodeBackground, LocalBackgroundMemory, MAX_BACKGROUND_BYTES, type SavedBackground, type BackgroundStatus } from '../src/practice/local-background.ts';

const file = (name = 'test.png') => new File(['synthetic image bytes'], name, { type: 'image/png', lastModified: 42 });
class Backend {
  value: SavedBackground | undefined;
  gate: Promise<void> | null = null;
  error: Error | null = null;
  async readBackground() { return this.value; }
  async writeBackground(image: SavedBackground) { if (this.gate) await this.gate; if (this.error) throw this.error; this.value = image; }
  async clearBackground() { if (this.error) throw this.error; this.value = undefined; }
}
function setup() {
  const backend = new Backend(), statuses: BackgroundStatus[] = [];
  return { backend, statuses, memory: new LocalBackgroundMemory(backend, s => statuses.push(s)) };
}
test('background records require actual bounded Blob bytes; absent old data stays absent', () => {
  assert.equal(decodeBackground(undefined), null);
  const value = { version: 1, blob: file(), name: 'test.png', type: '', lastModified: 0 };
  assert.equal(decodeBackground(value)?.blob.size, value.blob.size);
  for (const bad of [{ ...value, blob: 'blob:expired' }, { ...value, version: 2 }, { ...value, blob: new Blob() },
    { ...value, blob: new Blob([new Uint8Array(MAX_BACKGROUND_BYTES + 1)]) }, { ...value, lastModified: NaN }]) assert.throws(() => decodeBackground(bad));
});
test('failed replacement preserves preceding image and retry can save the current image', async () => {
  const { backend, statuses, memory } = setup();
  await memory.save(file('first.png'));
  backend.error = new DOMException('quota', 'QuotaExceededError');
  await memory.save(file('second.png'));
  assert.equal(backend.value?.name, 'first.png');
  assert.equal(statuses.at(-1)?.phase, 'error');
  assert.match(statuses.at(-1)!.message, /空間不足/);
  backend.error = null;
  await memory.save(file('second.png'));
  assert.equal((await memory.read())?.name, 'second.png');
  assert.equal(statuses.at(-1)?.phase, 'saved');
});
test('clear wins an in-flight background save and later selections can save again', async () => {
  const { backend, statuses, memory } = setup();
  let release!: () => void;
  backend.gate = new Promise(resolve => { release = resolve; });
  const pending = memory.save(file('pending.png'));
  await new Promise(resolve => setImmediate(resolve));
  const clear = memory.clear();
  release(); await pending; await clear;
  assert.equal(backend.value, undefined);
  assert.equal(statuses.at(-1)?.phase, 'cleared');
  assert.equal(statuses.filter(s => s.phase === 'saved').length, 0);
  backend.gate = null;
  await memory.save(file('latest.png'));
  assert.equal(backend.value?.name, 'latest.png');
});
