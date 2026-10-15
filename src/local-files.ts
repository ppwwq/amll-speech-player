const audioTypes: Record<string, string> = {
  mp3: 'audio/mpeg', wav: 'audio/wav', ogg: 'audio/ogg',
  m4a: 'audio/mp4', aac: 'audio/aac', flac: 'audio/flac',
};

export function isAudioFile(file: Pick<File, 'name' | 'type'>): boolean {
  return /\.(mp3|wav|ogg|m4a|aac|flac)$/i.test(file.name) || file.type.startsWith('audio/');
}

export function isCaptionFile(file: Pick<File, 'name' | 'type'>): boolean {
  // Empty MIME is common in Files providers; it is only a candidate, never proof
  // of valid captions. The parser must still find readable, timed lines.
  return /\.(lrc|ttml|yrc|lys|qrc|txt|ass|lqe|lyl|srt|spl)$/i.test(file.name)
    || file.type === 'text/plain' || file.type === '';
}

/** Validate locally without replacing the current track or uploading the file. */
export async function createPlayableAudioUrl(file: File): Promise<string> {
  if (!file.size || !isAudioFile(file)) throw new Error('Unsupported or empty audio file');
  const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
  // A provider can label an MP3 application/octet-stream (or even image/*).
  // Supply the known format to the decoder, which still validates the bytes.
  const type = audioTypes[extension] ?? file.type;
  const url = URL.createObjectURL(file.slice(0, file.size, type));
  const probe = document.createElement('audio');
  probe.preload = 'metadata';
  try {
    await new Promise<void>((resolve, reject) => {
      const finish = (error?: Error) => {
        clearTimeout(timeout);
        probe.onloadedmetadata = null;
        probe.onerror = null;
        error ? reject(error) : resolve();
      };
      const timeout = window.setTimeout(() => finish(new Error('Audio loading timed out')), 15000);
      probe.onloadedmetadata = () => finish(
        Number.isFinite(probe.duration) && probe.duration > 0
          ? undefined : new Error('Audio has no playable duration'),
      );
      probe.onerror = () => finish(new Error('Audio cannot be decoded'));
      probe.src = url;
      probe.load();
    });
    return url;
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  } finally {
    probe.removeAttribute('src');
    probe.load();
  }
}
