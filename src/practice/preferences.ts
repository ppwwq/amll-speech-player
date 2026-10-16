export const PREFERENCES_KEY = 'amll_speech_preferences_v1';
export const LEGACY_SETTINGS_KEY = 'amll_speech_background_settings_v1';
export const LEGACY_DRAG_KEY = 'amll_speech_drag_seek_v1';

const numbers = {
  playbackRate: [1, 0.1, 4], volume: [0.5, 0, 1],
  backgroundFlowSpeed: [4, 0, 10], backgroundMaskOpacity: [70, 0, 100],
  coverBlurLevel: [100, 0, 100], roundedCover: [55, 0, 100], coverRotationSpeed: [0, -60, 60],
  backgroundRenderScale: [1, 0.1, 1], backgroundFPS: [30, 1, 60],
  lyricAlignPosition: [0.4, 0, 1], wordFadeWidth: [0.5, 0.01, 10],
  backgroundLowFreqVolume: [1, 0, 1], fftDataRangeMin: [1, 1, 22050], fftDataRangeMax: [22050, 1, 22050],
  posYSpringMass: [1, 0.1, 10], posYSpringDamping: [15, 0.1, 50], posYSpringStiffness: [100, 1, 500],
  scaleSpringMass: [1, 0.1, 10], scaleSpringDamping: [20, 0.1, 50], scaleSpringStiffness: [100, 1, 500],
} as const;
const booleans = {
  loopPlay: true, dragSeekEnabled: true, showRemainingTime: false,
  backgroundDynamic: true, backgroundColorMask: true, showFPS: false, invertColors: false,
  marqueeEnabled: true, hidePassedLyrics: false, enableLyricBlur: true, enableLyricScale: true,
  enableLyricSpring: true, showTranslatedLyric: true, showRomanLyric: true, swapLyricPositions: false,
  showbgLyric: true, swapDuetsPositions: false, advanceLyricTiming: false, singleLyrics: false,
  posYSpringSoft: false, scaleSpringSoft: false,
};
const choices = {
  backgroundType: ['fluid', 'cover', 'solid'], lyricAlignAnchor: ['center', 'top', 'bottom'],
  coverStyle: ['normal', 'innerShadow', 'threeDShadow', 'longShadow', 'neumorphismA', 'neumorphismB', 'reflection', 'cd', 'vinyl', 'colored'],
} as const;
type NumericPreferences = { [K in keyof typeof numbers]: number };
type ChoicePreferences = { [K in keyof typeof choices]: (typeof choices)[K][number] };
export type Preferences = NumericPreferences & typeof booleans & ChoicePreferences & {
  backgroundMaskColor: string; manualDominantColor: string | null;
  manualDominantColorLight: string | null; manualDominantColorDark: string | null; controlPointCode: string;
};
export const PREFERENCE_DEFAULTS: Preferences = {
  ...Object.fromEntries(Object.entries(numbers).map(([key, range]) => [key, range[0]])) as NumericPreferences,
  ...booleans, backgroundType: 'fluid', lyricAlignAnchor: 'center', coverStyle: 'normal',
  backgroundMaskColor: '#FFFFFF', manualDominantColor: null, manualDominantColorLight: null,
  manualDominantColorDark: null, controlPointCode: '',
};

/** Existing mesh JSON formats, bounded before passing stored data to the renderer. */
export function validControlPointCode(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 100_000) return null;
  if (!value.trim()) return '';
  try {
    const data = JSON.parse(value);
    let width: number, height: number, points: unknown[];
    if (Array.isArray(data)) {
      if (typeof data[0] === 'number') [width, height, ...points] = data;
      else {
        points = data;
        width = Math.max(...data.map(p => Array.isArray(p) ? p[0] : NaN)) + 1;
        height = Math.max(...data.map(p => Array.isArray(p) ? p[1] : NaN)) + 1;
      }
    } else if (data && typeof data === 'object') ({ width, height, conf: points } = data);
    else return null;
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 2 || height < 2 || width > 64 || height > 64 ||
        !Array.isArray(points) || !points.length || points.length > width * height) return null;
    if (!points.every(p => Array.isArray(p) && p.length === 8 &&
      p.every(n => typeof n === 'number' && Number.isFinite(n) && Math.abs(n) <= 1e6) &&
      Number.isInteger(p[0]) && Number.isInteger(p[1]) && p[0] >= 0 && p[0] < width && p[1] >= 0 && p[1] < height)) return null;
    return JSON.stringify(data);
  } catch { return null; }
}

export function sanitizePreferences(input: unknown): { values: Partial<Preferences>; invalid: boolean } {
  const values: Record<string, unknown> = {};
  if (!input || typeof input !== 'object' || Array.isArray(input)) return { values, invalid: true };
  const raw = input as Record<string, unknown>;
  let invalid = false;
  for (const key of Object.keys(PREFERENCE_DEFAULTS)) {
    if (!Object.hasOwn(raw, key)) continue;
    const value = raw[key];
    if (Object.hasOwn(numbers, key)) {
      const [, min, max] = numbers[key as keyof typeof numbers];
      if (typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max) values[key] = value;
      else invalid = true;
    } else if (Object.hasOwn(booleans, key)) {
      if (typeof value === 'boolean') values[key] = value; else invalid = true;
    } else if (Object.hasOwn(choices, key)) {
      if ((choices[key as keyof typeof choices] as readonly unknown[]).includes(value)) values[key] = value; else invalid = true;
    } else if (key === 'controlPointCode') {
      const code = validControlPointCode(value);
      if (code !== null) values[key] = code; else invalid = true;
    } else if (value === null && key !== 'backgroundMaskColor' || typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value)) {
      values[key] = value;
    } else invalid = true;
  }
  if (Number(values.fftDataRangeMin ?? 1) > Number(values.fftDataRangeMax ?? 22050)) {
    delete values.fftDataRangeMin; delete values.fftDataRangeMax; invalid = true;
  }
  return { values: values as Partial<Preferences>, invalid };
}

export type PreferenceStatus = { phase: 'empty' | 'loaded' | 'saved' | 'error'; message: string };
type StorageAccess = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export class PreferenceMemory {
  private futureVersion = false;
  private storage: () => StorageAccess;
  private report: (status: PreferenceStatus) => void;
  constructor(storage: () => StorageAccess = () => localStorage,
    report: (status: PreferenceStatus) => void = () => {}) {
    this.storage = storage;
    this.report = report;
  }

  read(): Partial<Preferences> {
    this.futureVersion = false;
    try {
      const storage = this.storage(), text = storage.getItem(PREFERENCES_KEY);
      let raw: unknown, legacy = false, legacyInvalid = false;
      if (text !== null) {
        const record = JSON.parse(text);
        if (Number.isInteger(record?.version) && record.version > 1) {
          this.futureVersion = true;
          this.report({ phase: 'error', message: '設定版本無法讀取；保留原資料，本次變更暫不保存。' });
          return {};
        }
        if (record?.version !== 1) throw new Error('Invalid preference record');
        raw = record.values;
      } else {
        const old = storage.getItem(LEGACY_SETTINGS_KEY);
        try { raw = old ? JSON.parse(old) : {}; } catch { raw = {}; legacyInvalid = true; }
        legacy = old !== null;
        const drag = storage.getItem(LEGACY_DRAG_KEY);
        if (drag === 'true' || drag === 'false') {
          const sanitized = sanitizePreferences(raw);
          legacyInvalid ||= sanitized.invalid;
          raw = { ...sanitized.values, dragSeekEnabled: drag === 'true' };
          legacy = true;
        }
      }
      const { values, invalid } = sanitizePreferences(raw);
      this.report({ phase: invalid || legacyInvalid ? 'error' : text !== null || legacy ? 'loaded' : 'empty',
        message: invalid || legacyInvalid ? '已略過無效設定；有效項目已恢復，更改設定後會重新保存。'
          : text !== null || legacy ? '設定已恢復；更改後會自動保存於此瀏覽器。' : '設定更改後會自動保存於此瀏覽器。' });
      return values;
    } catch {
      this.report({ phase: 'error', message: '無法讀取保存設定；本次仍可調整，更改設定時會重試保存。' });
      return {};
    }
  }

  save(input: Preferences): boolean {
    if (this.futureVersion) return false;
    try {
      const { values, invalid } = sanitizePreferences(input);
      if (invalid) throw new Error('Invalid preferences');
      this.storage().setItem(PREFERENCES_KEY, JSON.stringify({ version: 1, values }));
      this.report({ phase: 'saved', message: '設定已自動保存於此瀏覽器。' });
      return true;
    } catch {
      this.report({ phase: 'error', message: '設定尚未保存（儲存空間不足或不可用）；本次仍生效，更改設定可重試。' });
      return false;
    }
  }
}
