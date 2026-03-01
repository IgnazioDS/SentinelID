declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export const TAURI_REQUIRED_MESSAGE =
  'This UI must be opened via the SentinelID desktop app.';

export function isTauriRuntimeAvailable(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  // Support both Tauri v1 and v2 runtime bridges in dev and packaged runs.
  return (
    typeof window.__TAURI_INTERNALS__ !== 'undefined' ||
    typeof window.__TAURI__ !== 'undefined' ||
    typeof window.__TAURI_IPC__ === 'function'
  );
}
