import { invoke } from '@tauri-apps/api/core';
import { ApiClientError } from './apiErrors';
import { TAURI_REQUIRED_MESSAGE, isTauriRuntimeAvailable } from './tauriRuntime';

interface EdgeInfo {
  base_url: string;
  token: string;
}

interface ErrorPayload {
  detail?: unknown;
  reason_codes?: string[];
}

interface SupportBundleResult {
  filename: string;
  createdAt: string | null;
}

export interface DiagnosticsResponse {
  device_id?: string;
  device_key_fingerprint?: string;
  outbox_pending_count?: number;
  dlq_count?: number;
  last_attempt?: string | null;
  last_success?: string | null;
  last_error_summary?: string | null;
  telemetry_flags?: {
    enabled?: boolean;
    runtime_available?: boolean;
    cloud_ingest_configured?: boolean;
  };
  telemetry?: {
    enabled?: boolean;
    last_export_attempt_time?: string | null;
    last_export_success_time?: string | null;
    last_export_error?: string | null;
    queue?: {
      max_size?: number;
      current_size?: number;
      wake_signals?: number;
      dropped_signals?: number;
    };
    outbox?: {
      pending_count?: number;
      dlq_count?: number;
      sent_count?: number;
    };
  };
  performance?: Record<string, {
    count?: number;
    mean_ms?: number | null;
    p50_ms?: number | null;
    p95_ms?: number | null;
  }>;
  frame_processing?: {
    max_fps?: number;
    processed_total?: number;
    dropped_rate_total?: number;
    dropped_backpressure_total?: number;
  };
}

function parseErrorPayload(raw: string): ErrorPayload {
  if (!raw) {
    return {};
  }
  try {
    return JSON.parse(raw) as ErrorPayload;
  } catch {
    return { detail: raw };
  }
}

function normalizeReasonCodes(payload: ErrorPayload): string[] {
  if (Array.isArray(payload.reason_codes)) {
    return payload.reason_codes;
  }
  if (
    payload.detail &&
    typeof payload.detail === 'object' &&
    Array.isArray((payload.detail as Record<string, unknown>).reason_codes)
  ) {
    return (payload.detail as Record<string, string[]>).reason_codes;
  }
  return [];
}

function detailText(payload: ErrorPayload): string {
  if (typeof payload.detail === 'string') {
    return payload.detail;
  }
  if (payload.detail && typeof payload.detail === 'object') {
    const nested = payload.detail as Record<string, unknown>;
    if (typeof nested.detail === 'string') {
      return nested.detail;
    }
    if (typeof nested.message === 'string') {
      return nested.message;
    }
    return JSON.stringify(nested);
  }
  return 'Unknown error';
}

function ensureTauriRuntime(): void {
  if (!isTauriRuntimeAvailable()) {
    throw new ApiClientError(TAURI_REQUIRED_MESSAGE, { kind: 'tauri' });
  }
}

async function getEdgeInfo(): Promise<EdgeInfo> {
  ensureTauriRuntime();
  try {
    // start_edge is idempotent and restarts Edge if child exited.
    return await invoke<EdgeInfo>('start_edge');
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new ApiClientError(`Unable to start Edge service: ${message}`, {
      kind: 'server',
      detail: message,
    });
  }
}

async function getCurrentEdgeInfo(): Promise<EdgeInfo> {
  ensureTauriRuntime();
  try {
    return await invoke<EdgeInfo>('get_edge_info');
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new ApiClientError(`Edge service is not running: ${message}`, {
      kind: 'network',
      detail: message,
    });
  }
}

async function killEdge(): Promise<void> {
  ensureTauriRuntime();
  await invoke('kill_edge');
}

async function doEdgeFetch(edge: EdgeInfo, path: string, method: string, body?: unknown): Promise<Response> {
  try {
    return await fetch(`${edge.base_url}/api/v1${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${edge.token}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new ApiClientError(`Network error calling ${path}: ${message}`, {
      kind: 'network',
      detail: message,
    });
  }
}

function buildHttpError(path: string, status: number, payload: ErrorPayload): ApiClientError {
  const reasonCodes = normalizeReasonCodes(payload);
  const detail = detailText(payload);

  if (status === 401 || status === 403) {
    return new ApiClientError(`Authorization failed for ${path}: ${detail}`, {
      kind: 'auth',
      status,
      reasonCodes,
      detail,
    });
  }

  return new ApiClientError(`API ${path} failed (${status}): ${detail}`, {
    kind: 'server',
    status,
    reasonCodes,
    detail,
  });
}

async function request(path: string, method: string, body?: unknown): Promise<any> {
  let edge = await getEdgeInfo();
  let response: Response;

  try {
    response = await doEdgeFetch(edge, path, method, body);
  } catch (error) {
    if (!(error instanceof ApiClientError) || error.kind !== 'network') {
      throw error;
    }
    edge = await getEdgeInfo();
    response = await doEdgeFetch(edge, path, method, body);
  }

  if (!response.ok && (response.status === 401 || response.status === 502 || response.status === 503)) {
    edge = await getEdgeInfo();
    response = await doEdgeFetch(edge, path, method, body);
  }

  if (!response.ok) {
    const raw = await response.text();
    throw buildHttpError(path, response.status, parseErrorPayload(raw));
  }

  return await response.json();
}

function cloudConfig(): { baseUrl: string; adminToken: string } {
  const baseUrl = (import.meta.env.VITE_CLOUD_BASE_URL as string | undefined)?.trim();
  const adminToken = (import.meta.env.VITE_ADMIN_TOKEN as string | undefined)?.trim();

  if (!baseUrl) {
    throw new ApiClientError(
      'Support bundle requires VITE_CLOUD_BASE_URL in desktop environment.',
      { kind: 'config' }
    );
  }
  if (!adminToken) {
    throw new ApiClientError(
      'Support bundle requires VITE_ADMIN_TOKEN in desktop environment.',
      { kind: 'config' }
    );
  }

  return { baseUrl: baseUrl.replace(/\/$/, ''), adminToken };
}

async function generateSupportBundle(window: '24h' | '7d' | '30d' = '24h'): Promise<SupportBundleResult> {
  const { baseUrl, adminToken } = cloudConfig();
  let response: Response;

  try {
    response = await fetch(`${baseUrl}/v1/admin/support-bundle?window=${window}&events_limit=100`, {
      method: 'POST',
      headers: {
        'X-Admin-Token': adminToken,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new ApiClientError(`Network error generating support bundle: ${message}`, {
      kind: 'network',
      detail: message,
    });
  }

  if (!response.ok) {
    const raw = await response.text();
    throw buildHttpError('/v1/admin/support-bundle', response.status, parseErrorPayload(raw));
  }

  const blob = await response.blob();
  const disposition = response.headers.get('content-disposition') ?? '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] ?? `support_bundle_${Date.now()}.tar.gz`;

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);

  return {
    filename,
    createdAt: response.headers.get('x-support-bundle-created-at'),
  };
}

const apiClient = {
  startEdge: getEdgeInfo,
  getCurrentEdgeInfo,
  killEdge,
  startEnroll: (targetFrames?: number) => request('/enroll/start', 'POST', { target_frames: targetFrames }),
  enrollFrame: (sessionId: string, frame: string) =>
    request('/enroll/frame', 'POST', { session_id: sessionId, frame }),
  commitEnroll: (sessionId: string, label: string) =>
    request('/enroll/commit', 'POST', { session_id: sessionId, label }),
  resetEnroll: (sessionId: string) => request('/enroll/reset', 'POST', { session_id: sessionId }),
  startAuth: () => request('/auth/start', 'POST', {}),
  authFrame: (sessionId: string, frame: string) =>
    request('/auth/frame', 'POST', { session_id: sessionId, frame }),
  finishAuth: (sessionId: string) => request('/auth/finish', 'POST', { session_id: sessionId }),
  getDiagnostics: (): Promise<DiagnosticsResponse> => request('/diagnostics', 'GET'),
  getTelemetrySettings: () => request('/settings/telemetry', 'GET'),
  updateTelemetrySettings: (enabled: boolean) =>
    request('/settings/telemetry', 'POST', { telemetry_enabled: enabled }),
  deleteIdentity: () =>
    request('/settings/delete_identity', 'POST', {
      clear_audit: true,
      clear_outbox: true,
      rotate_device_key: true,
    }),
  generateSupportBundle,
};

export type { EdgeInfo, SupportBundleResult };
export default apiClient;
