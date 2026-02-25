export type ApiErrorKind = 'tauri' | 'config' | 'network' | 'auth' | 'server';

interface ApiErrorOptions {
  kind: ApiErrorKind;
  status?: number;
  reasonCodes?: string[];
  detail?: string;
}

export class ApiClientError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly reasonCodes: string[];
  readonly detail?: string;

  constructor(message: string, options: ApiErrorOptions) {
    super(message);
    this.name = 'ApiClientError';
    this.kind = options.kind;
    this.status = options.status;
    this.reasonCodes = options.reasonCodes ?? [];
    this.detail = options.detail;
  }
}

export function toUserFacingError(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.kind === 'tauri') {
      return 'Desktop runtime not available. Open SentinelID from the desktop app.';
    }
    if (error.kind === 'config') {
      return error.message;
    }
    if (error.kind === 'network') {
      return 'Cannot reach local Edge service. Ensure Edge is running, then retry.';
    }
    if (error.kind === 'auth') {
      return 'Session authorization failed. Retry and let the app restart Edge.';
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}
