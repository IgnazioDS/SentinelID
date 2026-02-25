import { invoke } from '@tauri-apps/api/core';

interface EdgeInfo {
  base_url: string;
  token: string;
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

let edgeInfo: EdgeInfo | null = null;

async function getEdgeInfo(): Promise<EdgeInfo> {
  // start_edge is idempotent and restarts Edge if the child exited.
  const info = await invoke<EdgeInfo>('start_edge');
  edgeInfo = info;
  return info;
}

async function request(path: string, method: string, body?: unknown): Promise<any> {
  const doFetch = async (edge: EdgeInfo): Promise<Response> => fetch(`${edge.base_url}/api/v1${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${edge.token}`,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  let edge = await getEdgeInfo();
  let res: Response;
  try {
    res = await doFetch(edge);
  } catch {
    // Edge may have crashed/restarted between calls; refresh and retry once.
    edge = await getEdgeInfo();
    res = await doFetch(edge);
  }

  if (!res.ok && (res.status === 401 || res.status === 502 || res.status === 503)) {
    edge = await getEdgeInfo();
    res = await doFetch(edge);
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed: ${res.status} ${text || res.statusText}`);
  }

  return await res.json();
}

const apiClient = {
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
};

export default apiClient;
