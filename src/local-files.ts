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

export function waitForAudioMetadata(audio: HTMLAudioElement): Promise<void> {
  return new Promise((resolve, reject) => {
    const finish = (error?: Error) => {
      clearTimeout(timeout);
      audio.removeEventListener('loadedmetadata', ready);
      audio.removeEventListener('error', failed);
      error ? reject(error) : resolve();
    };
    const ready = () => finish(Number.isFinite(audio.duration) && audio.duration > 0
      ? undefined : new Error('Audio has no playable duration'));
    const failed = () => finish(new Error('Audio cannot be decoded'));
    const timeout = window.setTimeout(() => finish(new Error('Audio loading timed out')), 15000);
    audio.addEventListener('loadedmetadata', ready);
    audio.addEventListener('error', failed);
    if (audio.error) failed();
    else if (audio.readyState >= HTMLMediaElement.HAVE_METADATA) ready();
  });
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
    probe.src = url;
    probe.load();
    await waitForAudioMetadata(probe);
    return url;
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  } finally {
    probe.removeAttribute('src');
    probe.load();
  }
}
