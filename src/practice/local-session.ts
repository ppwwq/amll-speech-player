/** Local-only persistence. No file bytes or captions leave this origin. */
import type { BackgroundBackend, SavedBackground } from './local-background';
export const SESSION_DB = 'amll-local-session-v1';
export const CHECKPOINT_KEY = 'amll-local-position-v1';
export const PROGRESS_INTERVAL = 2000;

export interface SavedAudio { blob: Blob; name: string; type: string; lastModified: number }
export interface SavedCaptions { text: string; name: string; type: string; lastModified: number }
export interface SavedMedia {
  version: 1;
  id: string;
  audio: SavedAudio | null;
  captions: SavedCaptions | null;
}
export interface SavedProgress { id: string; position: number; delay: number; updatedAt: number }
export interface SavedSession { media: SavedMedia; progress: SavedProgress }
export type SavePhase = 'empty' | 'loading' | 'saving' | 'saved' | 'clearing' | 'cleared' | 'error' | 'detached';
export interface SaveStatus { phase: SavePhase; message: string }
export interface SessionBackend {
  read(): Promise<SavedSession | null>;
  write(session: SavedSession): Promise<void>;
  progress(progress: SavedProgress): Promise<boolean>;
  clear(): Promise<void>;
}

export class CorruptSessionError extends Error {
  constructor() { super('Saved session is damaged'); this.name = 'CorruptSessionError'; }
}

function validFileInfo(value: any): boolean {
  return value && typeof value.name === 'string' && value.name.length > 0
    && typeof value.type === 'string' && Number.isFinite(value.lastModified);
}
export function validProgress(value: any, id: string): value is SavedProgress {
  return !!value && value.id === id && Number.isFinite(value.position) && value.position >= 0
    && Number.isFinite(value.delay) && Number.isFinite(value.updatedAt);
}
export function decodeSession(media: any, progress: any): SavedSession | null {
  if (media === undefined) return null;
  if (!media || media.version !== 1 || typeof media.id !== 'string' || !media.id
    || (!media.audio && !media.captions)
    || (media.audio !== null && (!validFileInfo(media.audio) || !(media.audio.blob instanceof Blob) || !media.audio.blob.size))
    || (media.captions !== null && (!validFileInfo(media.captions) || typeof media.captions.text !== 'string' || !media.captions.text.trim()))) {
    throw new CorruptSessionError();
  }
  return { media, progress: validProgress(progress, media.id) ? progress
    : { id: media.id, position: 0, delay: 0, updatedAt: 0 } };
}

export class IndexedDBSessionStore implements SessionBackend, BackgroundBackend {
  private database: Promise<IDBDatabase> | null = null;

  private open(): Promise<IDBDatabase> {
    if (this.database) return this.database;
    this.database = new Promise<IDBDatabase>((resolve, reject) => {
      let expired = false;
      const timeout = setTimeout(() => {
        expired = true;
        reject(new Error('Storage open timed out'));
      }, 5000);
      const fail = (error: unknown) => { expired = true; clearTimeout(timeout); reject(error); };
      try {
        const request = indexedDB.open(SESSION_DB, 1);
        request.onupgradeneeded = () => {
          if (expired) { request.transaction?.abort(); return; }
          request.result.createObjectStore('media');
          request.result.createObjectStore('progress');
        };
        request.onerror = () => fail(request.error);
        request.onblocked = () => fail(new Error('Storage is blocked by another tab'));
        request.onsuccess = () => {
          clearTimeout(timeout);
          const db = request.result;
          if (expired) { db.close(); return; }
          db.onversionchange = () => { db.close(); this.database = null; };
          db.onclose = () => { this.database = null; };
          resolve(db);
        };
      } catch (error) { fail(error); }
    }).catch(error => { this.database = null; throw error; });
    return this.database;
  }

  private async transaction<T>(mode: IDBTransactionMode, run: (tx: IDBTransaction, result: (value: T) => void, fail: (error: unknown) => void) => void): Promise<T> {
    const db = await this.open();
    return new Promise<T>((resolve, reject) => {
      const tx = db.transaction(['media', 'progress'], mode);
      let value: T;
      let requestError: unknown;
      const timeout = setTimeout(() => {
        try { tx.abort(); } catch { /* already inactive */ }
        reject(new Error('Storage transaction timed out'));
      }, 10000);
      // Safari can auto-close transactions across await boundaries. All requests
      // are issued synchronously here or from an IDB request callback.
      tx.oncomplete = () => { clearTimeout(timeout); resolve(value); };
      tx.onerror = event => { requestError = (event.target as IDBRequest)?.error ?? tx.error; };
      tx.onabort = () => { clearTimeout(timeout); reject(requestError ?? tx.error ?? new Error('Storage aborted')); };
      const fail = (error: unknown) => {
        requestError = error;
        clearTimeout(timeout);
        try { tx.abort(); } catch { /* already inactive */ }
        reject(error);
      };
      try { run(tx, result => { value = result; }, fail); }
      catch (error) { fail(error); }
    });
  }

  async read(): Promise<SavedSession | null> {
    const raw = await this.transaction<{ media?: unknown; progress?: unknown }>('readonly', (tx, result) => {
      const values: { media?: unknown; progress?: unknown } = {};
      tx.objectStore('media').get('last').onsuccess = e => { values.media = (e.target as IDBRequest).result; };
      tx.objectStore('progress').get('last').onsuccess = e => { values.progress = (e.target as IDBRequest).result; };
      result(values);
    });
    return decodeSession(raw.media, raw.progress);
  }
  write(session: SavedSession): Promise<void> {
    return this.transaction('readwrite', (tx, result) => {
      tx.objectStore('media').put(session.media, 'last');
      tx.objectStore('progress').put(session.progress, 'last');
      result(undefined);
    });
  }
  progress(progress: SavedProgress): Promise<boolean> {
    return this.transaction('readwrite', (tx, result, fail) => {
      tx.objectStore('media').get('last').onsuccess = e => {
        // A late checkpoint (including one from another tab) cannot recreate
        // cleared data or change a different audio/caption pair.
        try {
          if ((e.target as IDBRequest).result?.id !== progress.id) { result(false); return; }
          tx.objectStore('progress').put(progress, 'last');
          result(true);
        } catch (error) { fail(error); }
      };
    });
  }
  clear(): Promise<void> {
    return this.transaction('readwrite', (tx, result) => {
      tx.objectStore('media').delete('last');
      tx.objectStore('progress').delete('last');
      result(undefined);
    });
  }
  readBackground(): Promise<unknown> {
    return this.transaction('readonly', (tx, result) => {
      tx.objectStore('media').get('background').onsuccess = e => result((e.target as IDBRequest).result);
    });
  }
  writeBackground(image: SavedBackground): Promise<void> {
    return this.transaction('readwrite', (tx, result) => { tx.objectStore('media').put(image, 'background'); result(undefined); });
  }
  clearBackground(): Promise<void> {
    return this.transaction('readwrite', (tx, result) => { tx.objectStore('media').delete('background'); result(undefined); });
  }
}

function failureMessage(error: unknown, clearing = false): string {
  if (clearing) return '未能清除，原有保存可能仍在。請重試清除。';
  if (error instanceof CorruptSessionError) return '保存內容損壞，無法完整恢復。請重新選檔或清除保存。';
  if ((error as { name?: string })?.name === 'QuotaExceededError') return '瀏覽器空間不足，這次變更未保存。可清除舊保存後重試。';
  return '本機儲存不可用或寫入失敗，這次變更未保存。原有保存可能仍在。';
}

/** Serial writes + generations prevent stale saves from winning over import/clear. */
export class LocalSessionMemory {
  private revision = 0;
  private media: SavedMedia | null = null;
  private position = 0;
  private delay = 0;
  private savedId: string | null = null;
  private failed = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private queue: Promise<void> = Promise.resolve();
  private lastProgress = '';

  private readonly backend: SessionBackend;
  private readonly notify: (status: SaveStatus) => void;
  constructor(backend: SessionBackend, notify: (status: SaveStatus) => void) {
    this.backend = backend;
    this.notify = notify;
  }

  async read(): Promise<SavedSession | null> {
    const session = await this.backend.read();
    if (session) {
      try {
        const checkpoint = JSON.parse(localStorage.getItem(CHECKPOINT_KEY) ?? 'null');
        if (validProgress(checkpoint, session.media.id) && checkpoint.updatedAt >= session.progress.updatedAt) session.progress = checkpoint;
      } catch { /* IndexedDB still works if localStorage is unavailable. */ }
    }
    return session;
  }
  adopt(session: SavedSession): void {
    this.invalidate();
    this.media = session.media;
    this.savedId = session.media.id;
    this.position = session.progress.position;
    this.delay = session.progress.delay;
    this.lastProgress = this.progressKey();
    this.notify({ phase: 'saved', message: '已從本機恢復，保持暫停。點播放即可繼續。' });
  }
  reportFailure(error: unknown): void { this.notify({ phase: 'error', message: failureMessage(error) }); }

  save(audio: SavedAudio | null, captions: SavedCaptions | null, position: number, delay: number): Promise<void> {
    this.invalidate();
    const id = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
    this.media = audio || captions ? { version: 1, id, audio, captions } : null;
    this.position = Number.isFinite(position) ? Math.max(0, position) : 0;
    this.delay = Number.isFinite(delay) ? delay : 0;
    if (!this.media) {
      this.notify({ phase: 'empty', message: '選入本機音訊或字幕後會自動保存。' });
      return this.queue;
    }
    const media = this.media, revision = this.revision;
    this.notify({ phase: 'saving', message: '正在保存本機檔案，請稍候再關閉。' });
    return this.enqueue(async () => {
      if (revision !== this.revision) return;
      const progress = this.progressValue();
      try {
        await this.backend.write({ media, progress });
        if (revision !== this.revision) return;
        this.savedId = media.id;
        this.lastProgress = `${progress.position}:${progress.delay}`;
        this.notify({ phase: 'saved', message: audio
          ? (captions ? '音訊與字幕已保存；播放進度會定期更新。' : '音訊已保存；尚未選入字幕。播放進度會定期更新。')
          : '字幕已保存在此瀏覽器；尚未選入音訊。' });
        this.updateProgress(this.position, this.delay);
      } catch (error) {
        if (revision !== this.revision) return;
        this.failed = true;
        this.reportFailure(error);
      }
    });
  }

  updateProgress(position: number, delay: number, flush = false): void {
    if (!Number.isFinite(position) || position < 0 || !Number.isFinite(delay)) return;
    this.position = position;
    this.delay = delay;
    if (!this.media || this.media.id !== this.savedId || this.failed || this.progressKey() === this.lastProgress) return;
    if (flush) {
      this.stopTimer();
      this.checkpoint();
      void this.writeProgress();
    } else if (!this.timer) {
      this.timer = setTimeout(() => { this.timer = null; void this.writeProgress(); }, PROGRESS_INTERVAL);
    }
  }
  /** A tiny synchronous checkpoint covers reload/pagehide; file data stays in IDB. */
  checkpoint(): void {
    if (!this.media || this.media.id !== this.savedId || this.failed) return;
    try { localStorage.setItem(CHECKPOINT_KEY, JSON.stringify(this.progressValue())); } catch { /* IDB is the fallback. */ }
  }
  private writeProgress(): Promise<void> {
    const revision = this.revision;
    return this.enqueue(async () => {
      if (!this.media || revision !== this.revision || this.failed || this.media.id !== this.savedId || this.progressKey() === this.lastProgress) return;
      const progress = this.progressValue();
      try {
        const written = await this.backend.progress(progress);
        if (revision !== this.revision) return;
        if (!written) throw new Error('Saved files changed in another tab');
        this.lastProgress = `${progress.position}:${progress.delay}`;
      } catch (error) {
        if (revision !== this.revision) return;
        this.failed = true;
        this.reportFailure(error);
      }
    });
  }
  clear(): Promise<void> {
    this.invalidate();
    this.media = null;
    const revision = this.revision;
    try { localStorage.removeItem(CHECKPOINT_KEY); } catch { /* An old ID cannot revive deleted media. */ }
    this.notify({ phase: 'clearing', message: '正在清除本機保存…' });
    // Never skip an explicitly requested clear, even if a newer import is queued.
    return this.enqueue(async () => {
      try {
        await this.backend.clear();
        if (revision === this.revision) this.notify({ phase: 'cleared', message: '已清除保存；目前仍可播放。再次選檔或按保存才會重新保存。' });
      } catch (error) {
        if (revision === this.revision) this.notify({ phase: 'error', message: failureMessage(error, true) });
      }
    });
  }
  detach(): void {
    this.invalidate();
    this.media = null;
    this.notify({ phase: 'detached', message: '目前內容未加入本機保存；原有保存仍保留。' });
  }
  private invalidate(): void {
    ++this.revision;
    this.stopTimer();
    this.savedId = null;
    this.failed = false;
    this.lastProgress = '';
  }
  private progressKey(): string { return `${this.position}:${this.delay}`; }
  private progressValue(): SavedProgress { return { id: this.media!.id, position: this.position, delay: this.delay, updatedAt: Date.now() }; }
  private stopTimer(): void { if (this.timer) clearTimeout(this.timer); this.timer = null; }
  private enqueue(task: () => Promise<void>): Promise<void> {
    this.queue = this.queue.then(task, task);
    return this.queue;
  }
}
