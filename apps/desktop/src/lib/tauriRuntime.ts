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
  return typeof window.__TAURI_INTERNALS__ !== 'undefined';
}
