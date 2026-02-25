'use client';

import Link from 'next/link';
import { useParams, useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { adminAPI, DeviceDetailResponse, EventSeriesResponse } from '../../../lib/api';
import { normalizeRange, rangeStartEpoch, shortId } from '../../../lib/time';
import { EmptyState, ErrorState, LoadingState } from '../../components/ui-state';

function formatBucketLabel(value: string) {
  const dt = new Date(value);
  return `${dt.getMonth() + 1}/${dt.getDate()} ${dt.getHours().toString().padStart(2, '0')}:00`;
}

export default function DeviceDetailPage() {
  const params = useParams<{ deviceId: string }>();
  const searchParams = useSearchParams();
  const range = normalizeRange(searchParams.get('range'));
  const deviceId = decodeURIComponent(params.deviceId);

  const [data, setData] = useState<DeviceDetailResponse | null>(null);
  const [series, setSeries] = useState<EventSeriesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const startTs = rangeStartEpoch(range);
        const endTs = Math.floor(Date.now() / 1000);
        const [detail, trend] = await Promise.all([
          adminAPI.getDeviceDetail(deviceId, { limit: 50, start_ts: startTs, end_ts: endTs }),
          adminAPI.getEventSeries({ window: range, device_id: deviceId, start_ts: startTs, end_ts: endTs }),
        ]);
        if (!mounted) return;
        setData(detail);
        setSeries(trend);
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : 'Failed to load device detail');
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    if (deviceId) {
      load();
    }

    return () => {
      mounted = false;
    };
  }, [deviceId, range]);

  if (loading) {
    return <LoadingState text="Loading device detail..." />;
  }

  if (error) {
    return <ErrorState message={error} action={<Link className="button subtle" href={`/devices?range=${range}`}>Back</Link>} />;
  }

  if (!data) {
    return <EmptyState title="No device data" description="Device may not exist in this environment." />;
  }

  return (
    <div>
      <h1 className="page-title">Device {shortId(data.device.device_id, 18)}</h1>
      <p className="page-subtitle">
        <Link className="button subtle" href={`/devices?range=${range}`}>Back to devices</Link>
      </p>

      <div className="card-grid">
        <div className="card">
          <p className="metric-label">Last Seen</p>
          <p className="metric-value" style={{ fontSize: 18 }}>{new Date(data.device.last_seen).toLocaleString()}</p>
        </div>
        <div className="card">
          <p className="metric-label">Outbox Pending</p>
          <p className="metric-value">{data.device.outbox_pending_count ?? 0}</p>
        </div>
        <div className="card">
          <p className="metric-label">DLQ</p>
          <p className="metric-value">{data.device.dlq_count ?? 0}</p>
        </div>
        <div className="card">
          <p className="metric-label">Events</p>
          <p className="metric-value">{data.device.event_count}</p>
        </div>
      </div>

      <section className="section">
        <h2>Outcome Breakdown</h2>
        <div className="card-grid">
          <div className="card"><p className="metric-label">ALLOW</p><p className="metric-value">{data.outcome_breakdown.allow}</p></div>
          <div className="card"><p className="metric-label">DENY</p><p className="metric-value">{data.outcome_breakdown.deny}</p></div>
          <div className="card"><p className="metric-label">ERROR</p><p className="metric-value">{data.outcome_breakdown.error}</p></div>
        </div>
      </section>

      {series ? (
        <section className="section">
          <h2>Reliability Trend</h2>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series.points}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="bucket_start" tickFormatter={formatBucketLabel} minTickGap={32} />
                <YAxis />
                <Tooltip labelFormatter={formatBucketLabel} />
                <Legend />
                <Line type="monotone" dataKey="events" stroke="#0466c8" name="Events" dot={false} />
                <Line type="monotone" dataKey="outbox_pending_avg" stroke="#f4a261" name="Outbox Avg" dot={false} />
                <Line type="monotone" dataKey="dlq_avg" stroke="#c1121f" name="DLQ Avg" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      ) : null}

      <section className="section">
        <h2>Recent Events (50)</h2>
        {data.recent_events.length === 0 ? (
          <EmptyState title="No events" description="No events found for the selected window." />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Outcome</th>
                  <th>Reason Codes</th>
                  <th>Request</th>
                  <th>Session</th>
                  <th>Ingested</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_events.map((event) => (
                  <tr key={event.event_id}>
                    <td>{shortId(event.event_id, 12)}</td>
                    <td><span className={`badge ${event.outcome}`}>{event.outcome}</span></td>
                    <td>{event.reason_codes.join(', ') || '-'}</td>
                    <td>{event.request_id ? shortId(event.request_id, 12) : '-'}</td>
                    <td>{event.session_id ? shortId(event.session_id, 12) : '-'}</td>
                    <td>{new Date(event.ingested_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
