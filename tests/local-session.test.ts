import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LocalSessionMemory, decodeSession, CHECKPOINT_KEY, PROGRESS_INTERVAL,
  type SavedSession, type SavedProgress, type SaveStatus } from '../src/practice/local-session.ts';

const audio = (name = 'test.mp3') => ({ name, type: 'audio/mpeg', lastModified: 42, blob: new Blob(['synthetic']) });
const captions = { name: 'test.LRC', type: '', lastModified: 42, text: '[00:00.00]Test' };
const turn = () => new Promise<void>(resolve => setImmediate(resolve));
function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>(r => { resolve = r; });
  return { promise, resolve };
}
class Backend {
  value: SavedSession | null = null;
  writes = 0;
  progressWrites = 0;
  events: string[] = [];
  gate: Promise<void> | null = null;
  error: Error | null = null;
  async read() { return this.value ? structuredClone(this.value) : null; }
  async write(value: SavedSession) {
    this.writes++; this.events.push('write:'+value.media.audio?.name);
    if (this.gate) await this.gate;
    if (this.error) throw this.error;
    this.value = structuredClone(value);
  }
  async progress(progress: SavedProgress) {
    this.progressWrites++;
    if (this.error) throw this.error;
    if (this.value?.media.id !== progress.id) return false;
    this.value.progress = progress;
    return true;
  }
  async clear() {
    this.events.push('clear');
    if (this.error) throw this.error;
    this.value = null;
  }
}
function setup() {
  const backend = new Backend(), statuses: SaveStatus[] = [];
  const memory = new LocalSessionMemory(backend, status => statuses.push(status));
  return { backend, statuses, memory };
}

test('stored shapes reject corrupt files; foreign/bad progress never attaches to a pair', () => {
  const media = { version: 1, id: 'a', audio: audio(), captions };
  assert.equal(decodeSession(undefined, undefined), null);
  for (const value of [null, {}, { ...media, version: 2 }, { ...media, audio: { ...audio(), blob: 'not a Blob' } },
    { ...media, captions: { ...captions, text: '' } }, { ...media, audio: null, captions: null }]) {
    assert.throws(() => decodeSession(value, null), { name: 'CorruptSessionError' });
  }
  for (const progress of [null, { id: 'b', position: 20, delay: 0, updatedAt: 2 }, { id: 'a', position: NaN, delay: 0, updatedAt: 2 }]) {
    assert.equal(decodeSession(media, progress)?.progress.position, 0);
  }
});

test('only a completed write can report saved; quota failures keep the earlier pair', async () => {
  const { memory, backend, statuses } = setup(), gate = deferred();
  backend.gate = gate.promise;
  const pending = memory.save(audio(), captions, 4, 20);
  await turn();
  assert.equal(statuses.at(-1)?.phase, 'saving');
  assert.equal(backend.value, null);
  gate.resolve(); await pending;
  assert.equal(statuses.at(-1)?.phase, 'saved');
  const prior = backend.value;
  backend.error = Object.assign(new Error('full'), { name: 'QuotaExceededError' });
  await memory.save(audio('next.mp3'), null, 0, 0);
  assert.equal(statuses.at(-1)?.phase, 'error');
  assert.match(statuses.at(-1)!.message, /空間不足/);
  assert.equal(backend.value, prior);
});

test('a delayed old write cannot report success over a newer pending save', async () => {
  const { memory, backend, statuses } = setup(), gate = deferred();
  backend.gate = gate.promise;
  const first = memory.save(audio('first.mp3'), captions, 15, 0);
  await turn();
  const second = memory.save(audio('second.mp3'), null, 0, 0);
  const latest = memory.save(audio('latest.mp3'), captions, 2, 0);
  gate.resolve(); await Promise.all([first, second, latest]);
  assert.deepEqual(backend.events, ['write:first.mp3', 'write:latest.mp3']);
  assert.equal(backend.value?.media.audio?.name, 'latest.mp3');
  assert.equal(statuses.filter(s => s.phase === 'saved').length, 1);
});

test('clear wins over an in-flight save and disables later progress writes', async () => {
  const { memory, backend, statuses } = setup(), gate = deferred();
  backend.gate = gate.promise;
  const pending = memory.save(audio(), captions, 12, 0);
  await turn();
  const cleared = memory.clear();
  assert.equal(statuses.at(-1)?.phase, 'clearing');
  gate.resolve(); await Promise.all([pending, cleared]);
  assert.equal(backend.value, null);
  assert.equal(statuses.at(-1)?.phase, 'cleared');
  memory.updateProgress(25, 0, true); await turn();
  assert.equal(backend.progressWrites, 0);
  assert.equal(statuses.filter(s => s.phase === 'saved').length, 0);
});

test('a new selection after clear is saved after deletion, with its own captions', async () => {
  const { memory, backend } = setup(), gate = deferred();
  backend.gate = gate.promise;
  const first = memory.save(audio(), captions, 0, 0); await turn();
  const clear = memory.clear();
  const next = memory.save(audio('new.mp3'), null, 0, 0);
  gate.resolve(); await Promise.all([first, clear, next]);
  assert.deepEqual(backend.events, ['write:test.mp3', 'clear', 'write:new.mp3']);
  assert.equal(backend.value?.media.audio?.name, 'new.mp3');
  assert.equal(backend.value?.media.captions, null);
});

test('progress is throttled and stores only the latest position without rewriting audio', async () => {
  const { memory, backend } = setup();
  await memory.save(audio(), captions, 0, 0);
  for (let i = 1; i <= 50; i++) memory.updateProgress(i, 150);
  assert.equal(backend.progressWrites, 0);
  await new Promise(resolve => setTimeout(resolve, PROGRESS_INTERVAL + 30));
  assert.equal(backend.progressWrites, 1);
  assert.equal(backend.writes, 1);
  assert.equal(backend.value?.progress.position, 50);
  memory.updateProgress(51, 150, true); await turn();
  assert.equal(backend.value?.progress.position, 51);
});

test('checkpoint restore checks the pair ID and cannot revive deleted files', async () => {
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  } });
  try {
    const { memory, backend } = setup();
    await memory.save(audio(), captions, 0, 0);
    memory.updateProgress(11, 200); memory.checkpoint();
    assert.equal((await memory.read())?.progress.position, 11);
    values.set(CHECKPOINT_KEY, JSON.stringify({ id: 'other', position: 99, delay: 0, updatedAt: Date.now() }));
    assert.equal((await memory.read())?.progress.position, 0);
    await memory.clear();
    assert.equal(await memory.read(), null);
    assert.equal(backend.value, null);
  } finally { delete (globalThis as any).localStorage; }
});

test('a lost pair or failed clear reports failure and does not claim deletion', async () => {
  const { memory, backend, statuses } = setup();
  await memory.save(audio(), captions, 0, 0);
  backend.value = null; // Another tab cleared it.
  memory.updateProgress(10, 0, true); await turn();
  assert.equal(statuses.at(-1)?.phase, 'error');
  backend.error = new Error('Storage unavailable');
  await memory.clear();
  assert.equal(statuses.at(-1)?.phase, 'error');
  assert.match(statuses.at(-1)!.message, /未能清除/);
});
