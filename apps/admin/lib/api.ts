/**
 * Cloud API client through same-origin admin proxy.
 */

const API_PROXY_BASE = '/api/cloud';
interface FetchOptions extends RequestInit {}

async function fetchWithAuth(endpoint: string, options: FetchOptions = {}) {
  const fetchOptions = options;

  const headers = new Headers(fetchOptions.headers);
  headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_PROXY_BASE}${endpoint}`, {
    ...fetchOptions,
    headers,
    cache: 'no-store',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error((error as { detail?: string } | null)?.detail || `API error: ${response.status}`);
  }

  return response.json();
}

async function fetchBlobWithAuth(endpoint: string, options: FetchOptions = {}) {
  const fetchOptions = options;

  const headers = new Headers(fetchOptions.headers);
  const response = await fetch(`${API_PROXY_BASE}${endpoint}`, {
    ...fetchOptions,
    headers,
    cache: 'no-store',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error((error as { detail?: string } | null)?.detail || `API error: ${response.status}`);
  }

  return response;
}

export type TimeRange = '24h' | '7d' | '30d';

export interface Event {
  event_id: string;
  device_id: string;
  timestamp: number;
  event_type: string;
  outcome: string;
  reason_codes: string[];
  liveness_passed?: boolean;
  similarity_score?: number;
  risk_score?: number;
  session_duration_seconds?: number;
  session_id?: string;
  request_id?: string;
  outbox_pending_count?: number;
  dlq_count?: number;
  last_error_summary?: string;
  audit_event_hash?: string;
  ingested_at: string;
}

export interface EventsResponse {
  events: Event[];
  total: number;
  limit: number;
  offset: number;
  has_next: boolean;
}

export interface DeviceHealth {
  device_id: string;
  last_seen: string;
  event_count: number;
  outbox_pending_count?: number;
  dlq_count?: number;
  last_error_summary?: string;
  last_request_id?: string;
  last_session_id?: string;
}

export interface StatsResponse {
  window: TimeRange;
  window_seconds: number;
  window_started_at: string;
  total_devices: number;
  active_devices: number;
  active_devices_window: number;
  total_events: number;
  window_events: number;
  allow_count: number;
  deny_count: number;
  error_count: number;
  liveness_failure_rate: number;
  latency_p50_ms?: number;
  latency_p95_ms?: number;
  ingest_success_count: number;
  ingest_fail_count: number;
  events_ingested_count: number;
  ingest_window_seconds: number;
  risk_distribution: {
    low: number;
    medium: number;
    high: number;
  };
  outbox_pending_total: number;
  dlq_total: number;
  device_health: DeviceHealth[];
}

export interface EventSeriesPoint {
  bucket_start: string;
  events: number;
  allow: number;
  deny: number;
  error: number;
  outbox_pending_avg?: number;
  dlq_avg?: number;
}

export interface EventSeriesResponse {
  window: TimeRange;
  bucket: 'hour' | 'day';
  start: string;
  end: string;
  total_events: number;
  outcome_breakdown: {
    allow: number;
    deny: number;
    error: number;
  };
  points: EventSeriesPoint[];
}

export interface Device {
  device_id: string;
  registered_at: string;
  last_seen: string;
  is_active: boolean;
  event_count: number;
  outbox_pending_count?: number;
  dlq_count?: number;
  last_error_summary?: string;
  last_request_id?: string;
  last_session_id?: string;
}

export interface DevicesResponse {
  devices: Device[];
  total: number;
  limit: number;
  offset: number;
  has_next: boolean;
}

export interface DeviceDetailResponse {
  device: Device;
  recent_events: Event[];
  outcome_breakdown: {
    allow: number;
    deny: number;
    error: number;
  };
}

export interface SupportBundleResponse {
  blob: Blob;
  filename: string;
  createdAt?: string;
}

export const adminAPI = {
  async getEvents(params?: {
    limit?: number;
    offset?: number;
    device_id?: string;
    request_id?: string;
    session_id?: string;
    outcome?: string;
    reason_code?: string;
    start_ts?: number;
    end_ts?: number;
    q?: string;
  }): Promise<EventsResponse> {
    const query = new URLSearchParams();
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.offset !== undefined) query.append('offset', params.offset.toString());
    if (params?.device_id) query.append('device_id', params.device_id);
    if (params?.request_id) query.append('request_id', params.request_id);
    if (params?.session_id) query.append('session_id', params.session_id);
    if (params?.outcome) query.append('outcome', params.outcome);
    if (params?.reason_code) query.append('reason_code', params.reason_code);
    if (params?.start_ts) query.append('start_ts', params.start_ts.toString());
    if (params?.end_ts) query.append('end_ts', params.end_ts.toString());
    if (params?.q) query.append('q', params.q);

    return fetchWithAuth(`/v1/admin/events${query.toString() ? '?' + query.toString() : ''}`);
  },

  async getEventSeries(params?: {
    window?: TimeRange;
    device_id?: string;
    start_ts?: number;
    end_ts?: number;
  }): Promise<EventSeriesResponse> {
    const query = new URLSearchParams();
    if (params?.window) query.append('window', params.window);
    if (params?.device_id) query.append('device_id', params.device_id);
    if (params?.start_ts) query.append('start_ts', params.start_ts.toString());
    if (params?.end_ts) query.append('end_ts', params.end_ts.toString());

    return fetchWithAuth(`/v1/admin/events/series${query.toString() ? '?' + query.toString() : ''}`);
  },

  async getStats(window: TimeRange = '24h'): Promise<StatsResponse> {
    return fetchWithAuth(`/v1/admin/stats?window=${window}`);
  },

  async getDevices(params?: {
    limit?: number;
    offset?: number;
  }): Promise<DevicesResponse> {
    const query = new URLSearchParams();
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.offset !== undefined) query.append('offset', params.offset.toString());

    return fetchWithAuth(`/v1/admin/devices${query.toString() ? '?' + query.toString() : ''}`);
  },

  async getDeviceDetail(deviceId: string, params?: {
    limit?: number;
    start_ts?: number;
    end_ts?: number;
  }): Promise<DeviceDetailResponse> {
    const query = new URLSearchParams();
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.start_ts) query.append('start_ts', params.start_ts.toString());
    if (params?.end_ts) query.append('end_ts', params.end_ts.toString());

    return fetchWithAuth(
      `/v1/admin/devices/${encodeURIComponent(deviceId)}${query.toString() ? '?' + query.toString() : ''}`
    );
  },

  async generateSupportBundle(params?: {
    window?: TimeRange;
    events_limit?: number;
  }): Promise<SupportBundleResponse> {
    const query = new URLSearchParams();
    if (params?.window) query.append('window', params.window);
    if (params?.events_limit) query.append('events_limit', params.events_limit.toString());

    const response = await fetchBlobWithAuth(
      `/v1/admin/support-bundle${query.toString() ? '?' + query.toString() : ''}`,
      { method: 'POST' }
    );

    const disposition = response.headers.get('content-disposition') || '';
    const filenameMatch = disposition.match(/filename="?([^\"]+)"?/i);
    const filename = filenameMatch?.[1] || `support_bundle_${Date.now()}.tar.gz`;

    return {
      blob: await response.blob(),
      filename,
      createdAt: response.headers.get('x-support-bundle-created-at') || undefined,
    };
  },
};
