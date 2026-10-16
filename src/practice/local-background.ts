/** Original local image bytes only; object URLs are recreated on each visit. */
export const MAX_BACKGROUND_BYTES = 20 * 1024 * 1024;
export interface SavedBackground { version: 1; blob: Blob; name: string; type: string; lastModified: number }
export interface BackgroundBackend {
  readBackground(): Promise<unknown>;
  writeBackground(image: SavedBackground): Promise<void>;
  clearBackground(): Promise<void>;
}
export interface BackgroundStatus { phase: 'empty' | 'loading' | 'saving' | 'saved' | 'clearing' | 'cleared' | 'error' | 'detached'; message: string }
export function decodeBackground(value: any): SavedBackground | null {
  if (value === undefined || value === null) return null;
  if (value.version !== 1 || !(value.blob instanceof Blob) || !value.blob.size || value.blob.size > MAX_BACKGROUND_BYTES
    || typeof value.name !== 'string' || !value.name || typeof value.type !== 'string' || !Number.isFinite(value.lastModified)) {
    throw new Error('Saved background is damaged or unsupported');
  }
  return { version: 1, blob: value.blob, name: value.name, type: value.type, lastModified: value.lastModified };
}

export class LocalBackgroundMemory {
  private revision = 0;
  private queue: Promise<void> = Promise.resolve();
  private readonly backend: BackgroundBackend;
  private readonly notify: (status: BackgroundStatus) => void;
  constructor(backend: BackgroundBackend, notify: (status: BackgroundStatus) => void) { this.backend = backend; this.notify = notify; }
  async read() { return decodeBackground(await this.backend.readBackground()); }
  cancelPending() { ++this.revision; }
  reportFailure(error: unknown, clearing = false) {
    this.notify({ phase: 'error', message: clearing ? '背景未能清除，原有保存可能仍在。請重試。'
      : (error as { name?: string })?.name === 'QuotaExceededError'
        ? '空間不足，這張背景未保存。先前保存仍保留；請騰出空間或選較小圖片後重試。'
        : '背景儲存不可用、內容損壞或寫入失敗。請重新選圖或重試；先前保存可能仍在。' });
  }
  save(file: File): Promise<void> {
    const revision = ++this.revision;
    const image = decodeBackground({ version: 1, blob: file, name: file.name, type: file.type, lastModified: file.lastModified })!;
    this.notify({ phase: 'saving', message: '正在保存背景圖片，請稍候再關閉。' });
    return this.enqueue(async () => {
      if (revision !== this.revision) return;
      try {
        await this.backend.writeBackground(image);
        if (revision === this.revision) this.notify({ phase: 'saved', message: '背景圖片已保存在此瀏覽器，重新開啟可恢復。' });
      } catch (error) { if (revision === this.revision) this.reportFailure(error); }
    });
  }
  clear(): Promise<void> {
    const revision = ++this.revision;
    this.notify({ phase: 'clearing', message: '正在清除背景保存…' });
    return this.enqueue(async () => {
      try {
        await this.backend.clearBackground();
        if (revision === this.revision) this.notify({ phase: 'cleared', message: '已清除背景圖片保存。' });
      } catch (error) { if (revision === this.revision) this.reportFailure(error, true); }
    });
  }
  private enqueue(action: () => Promise<void>) { this.queue = this.queue.then(action, action); return this.queue; }
}
