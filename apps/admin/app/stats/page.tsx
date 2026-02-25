'use client';

import { useEffect, useState } from 'react';
import { adminAPI, StatsResponse } from '../../lib/api';
import Link from 'next/link';

export default function StatsPage() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadStats() {
      try {
        setLoading(true);
        setError(null);
        const response = await adminAPI.getStats();
        setStats(response);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load stats');
      } finally {
        setLoading(false);
      }
    }

    loadStats();
  }, []);

  const StatCard = ({ label, value, color = '#007bff' }: { label: string; value: string | number; color?: string }) => (
    <div
      style={{
        padding: '20px',
        backgroundColor: '#f9f9f9',
        borderRadius: '8px',
        border: `2px solid ${color}`,
        textAlign: 'center',
        minWidth: '150px',
      }}
    >
      <div style={{ fontSize: '14px', color: '#666', marginBottom: '10px' }}>
        {label}
      </div>
      <div style={{ fontSize: '28px', fontWeight: 'bold', color }}>{value}</div>
    </div>
  );

  return (
    <div style={{ padding: '20px' }}>
      <div style={{ marginBottom: '20px' }}>
        <Link href="/" style={{ marginRight: '20px' }}>
          Home
        </Link>
        <Link href="/events" style={{ marginRight: '20px' }}>
          Events
        </Link>
        <Link href="/devices">Devices</Link>
      </div>

      <h1>Service Statistics</h1>

      {error && (
        <div style={{ color: 'red', marginBottom: '20px', padding: '10px', backgroundColor: '#ffe0e0', borderRadius: '4px' }}>
          {error}
        </div>
      )}

      {loading ? (
        <p>Loading statistics...</p>
      ) : stats ? (
        <>
          <h2 style={{ marginTop: '30px', marginBottom: '15px' }}>Devices</h2>
          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '30px' }}>
            <StatCard label="Total Devices" value={stats.total_devices} color="#28a745" />
            <StatCard label="Active Devices" value={stats.active_devices} color="#17a2b8" />
          </div>

          <h2 style={{ marginTop: '30px', marginBottom: '15px' }}>Events</h2>
          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '30px' }}>
            <StatCard label="Total Events" value={stats.total_events} color="#007bff" />
            <StatCard label="Allow" value={stats.allow_count} color="#28a745" />
            <StatCard label="Deny" value={stats.deny_count} color="#dc3545" />
            <StatCard label="Error" value={stats.error_count} color="#ffc107" />
          </div>

          <h2 style={{ marginTop: '30px', marginBottom: '15px' }}>Quality Metrics</h2>
          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
            <div
              style={{
                padding: '20px',
                backgroundColor: '#f9f9f9',
                borderRadius: '8px',
                border: '2px solid #6f42c1',
                minWidth: '200px',
              }}
            >
              <div style={{ fontSize: '14px', color: '#666', marginBottom: '10px' }}>
                Liveness Failure Rate
              </div>
              <div style={{ fontSize: '28px', fontWeight: 'bold', color: '#6f42c1' }}>
                {stats.liveness_failure_rate.toFixed(2)}%
              </div>
            </div>

            <div
              style={{
                padding: '20px',
                backgroundColor: '#f9f9f9',
                borderRadius: '8px',
                border: '2px solid #20c997',
                minWidth: '200px',
              }}
            >
              <div style={{ fontSize: '14px', color: '#666', marginBottom: '10px' }}>
                Allow Rate
              </div>
              <div style={{ fontSize: '28px', fontWeight: 'bold', color: '#20c997' }}>
                {stats.total_events > 0
                  ? ((stats.allow_count / stats.total_events) * 100).toFixed(2)
                  : 0}
                %
              </div>
            </div>

            <div
              style={{
                padding: '20px',
                backgroundColor: '#f9f9f9',
                borderRadius: '8px',
                border: '2px solid #0d6efd',
                minWidth: '220px',
              }}
            >
              <div style={{ fontSize: '14px', color: '#666', marginBottom: '10px' }}>
                Latency p50 / p95
              </div>
              <div style={{ fontSize: '28px', fontWeight: 'bold', color: '#0d6efd' }}>
                {stats.latency_p50_ms !== undefined && stats.latency_p50_ms !== null
                  ? `${stats.latency_p50_ms.toFixed(0)} / ${stats.latency_p95_ms?.toFixed(0) ?? '0'} ms`
                  : 'n/a'}
              </div>
            </div>
          </div>

          <h2 style={{ marginTop: '30px', marginBottom: '15px' }}>Risk Distribution</h2>
          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
            <StatCard label="Risk Low" value={stats.risk_distribution.low} color="#28a745" />
            <StatCard label="Risk Medium" value={stats.risk_distribution.medium} color="#ffc107" />
            <StatCard label="Risk High" value={stats.risk_distribution.high} color="#dc3545" />
          </div>

          <h2 style={{ marginTop: '30px', marginBottom: '15px' }}>Ingest Reliability</h2>
          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
            <StatCard label="Ingest Success" value={stats.ingest_success_count} color="#28a745" />
            <StatCard label="Ingest Failures" value={stats.ingest_fail_count} color="#dc3545" />
            <StatCard label="Events Ingested" value={stats.events_ingested_count} color="#0d6efd" />
            <StatCard label="Window (s)" value={stats.ingest_window_seconds} color="#6f42c1" />
          </div>

          <h2 style={{ marginTop: '30px', marginBottom: '15px' }}>Device Health</h2>
          <div style={{ overflowX: 'auto' }}>
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                marginBottom: '20px',
              }}
            >
              <thead>
                <tr style={{ backgroundColor: '#f0f0f0' }}>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Device ID
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Last Seen
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Events
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Outbox Pending
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    DLQ
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Last Export Error
                  </th>
                </tr>
              </thead>
              <tbody>
                {stats.device_health.map((device) => (
                  <tr key={device.device_id}>
                    <td style={{ padding: '10px', border: '1px solid #ddd', fontSize: '12px' }}>
                      {device.device_id}
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', fontSize: '12px' }}>
                      {new Date(device.last_seen).toLocaleString()}
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd' }}>
                      {device.event_count}
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd' }}>
                      {device.outbox_pending_count ?? '-'}
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd' }}>
                      {device.dlq_count ?? '-'}
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', fontSize: '12px' }}>
                      {device.last_error_summary ?? '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
