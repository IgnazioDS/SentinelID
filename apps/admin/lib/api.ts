/**
 * Cloud API client with admin token support.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const ADMIN_TOKEN = process.env.NEXT_PUBLIC_ADMIN_TOKEN || 'dev-admin-token';

interface FetchOptions extends RequestInit {
  includeToken?: boolean;
}

async function fetchWithAuth(endpoint: string, options: FetchOptions = {}) {
  const { includeToken = true, ...fetchOptions } = options;

  const headers = new Headers(fetchOptions.headers);
  headers.set('Content-Type', 'application/json');

  if (includeToken) {
    headers.set('X-Admin-Token', ADMIN_TOKEN);
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `API error: ${response.status}`);
  }

  return response.json();
}

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

export interface StatsResponse {
  total_devices: number;
  active_devices: number;
  total_events: number;
  allow_count: number;
  deny_count: number;
  error_count: number;
  liveness_failure_rate: number;
  latency_p50_ms?: number;
  latency_p95_ms?: number;
  risk_distribution: {
    low: number;
    medium: number;
    high: number;
  };
}

export interface Device {
  device_id: string;
  registered_at: string;
  last_seen: string;
  is_active: boolean;
  event_count: number;
}

export interface DevicesResponse {
  devices: Device[];
  total: number;
  limit: number;
  offset: number;
  has_next: boolean;
}

export const adminAPI = {
  /**
   * Get telemetry events with optional filtering and pagination.
   */
  async getEvents(params?: {
    limit?: number;
    offset?: number;
    device_id?: string;
    outcome?: string;
  }): Promise<EventsResponse> {
    const query = new URLSearchParams();
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.offset) query.append('offset', params.offset.toString());
    if (params?.device_id) query.append('device_id', params.device_id);
    if (params?.outcome) query.append('outcome', params.outcome);

    return fetchWithAuth(
      `/v1/admin/events${query.toString() ? '?' + query.toString() : ''}`
    );
  },

  /**
   * Get service statistics.
   */
  async getStats(): Promise<StatsResponse> {
    return fetchWithAuth('/v1/admin/stats');
  },

  /**
   * Get registered devices with pagination.
   */
  async getDevices(params?: {
    limit?: number;
    offset?: number;
  }): Promise<DevicesResponse> {
    const query = new URLSearchParams();
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.offset) query.append('offset', params.offset.toString());

    return fetchWithAuth(
      `/v1/admin/devices${query.toString() ? '?' + query.toString() : ''}`
    );
  },
};
