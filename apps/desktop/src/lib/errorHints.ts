import { ApiClientError } from './apiErrors';

export function recoveryHint(error: unknown): string | null {
  if (!(error instanceof ApiClientError)) {
    return null;
  }
  switch (error.kind) {
    case 'network':
      return 'Check Edge service status at the bottom strip, then use Restart if needed.';
    case 'auth':
      return 'Restart the login/enrollment session to refresh runtime credentials.';
    case 'config':
      return 'Set required environment variables and relaunch the desktop app.';
    case 'tauri':
      return 'Launch this UI through the SentinelID desktop app, not a browser URL.';
    default:
      return null;
  }
}
