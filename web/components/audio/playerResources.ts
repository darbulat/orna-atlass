type PlayerAudioResource = Pick<
  HTMLAudioElement,
  | "load"
  | "pause"
  | "removeAttribute"
  | "ondurationchange"
  | "onended"
  | "onerror"
  | "onloadedmetadata"
  | "onstalled"
  | "ontimeupdate"
>;

export function isHlsStream(url: string): boolean {
  try {
    return new URL(url, "https://orna-atlas.invalid").pathname.endsWith(".m3u8");
  } catch {
    return false;
  }
}

export function detachAudio(audio: PlayerAudioResource) {
  audio.ontimeupdate = null;
  audio.onloadedmetadata = null;
  audio.ondurationchange = null;
  audio.onended = null;
  audio.onerror = null;
  audio.onstalled = null;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
}

export function disposePlayerResources({
  audio,
  abortController,
  refreshTimerId,
  clearTimer,
}: {
  audio: PlayerAudioResource | null;
  abortController: AbortController | null;
  refreshTimerId: number | null;
  clearTimer: (timerId: number) => void;
}) {
  if (refreshTimerId !== null) {
    clearTimer(refreshTimerId);
  }
  abortController?.abort();
  if (audio) {
    detachAudio(audio);
  }
}
