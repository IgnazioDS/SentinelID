'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { adminAPI, Device } from '../../lib/api';
import { copyToClipboard, normalizeRange, shortId } from '../../lib/time';
import { EmptyState, ErrorState, LoadingState } from '../components/ui-state';

export default function DevicesPage() {
  const searchParams = useSearchParams();
  const range = normalizeRange(searchParams.get('range'));

  const [devices, setDevices] = useState<Device[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [copyMessage, setCopyMessage] = useState('');

  useEffect(() => {
    let mounted = true;

    async function loadDevices() {
      try {
        setLoading(true);
        setError(null);
        const response = await adminAPI.getDevices({ limit, offset });
        if (!mounted) return;
        setDevices(response.devices);
        setTotal(response.total);
        setHasNext(response.has_next);
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : 'Failed to load devices');
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    loadDevices();
    return () => {
      mounted = false;
    };
  }, [limit, offset]);

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  if (loading && devices.length === 0) {
    return <LoadingState text="Loading devices..." />;
  }

  return (
    <div>
      <h1 className="page-title">Devices</h1>
      <p className="page-subtitle">Device reliability and queue health. Window selected: {range}</p>

      {copyMessage ? <p className="muted">{copyMessage}</p> : null}

      {error ? (
        <ErrorState message={error} action={<button className="button subtle" onClick={() => window.location.reload()}>Retry</button>} />
      ) : null}

      {!loading && devices.length === 0 ? (
        <EmptyState title="No registered devices" description="Ingest telemetry to see active devices." />
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Device</th>
                  <th>Last Seen</th>
                  <th>Outbox Pending</th>
                  <th>DLQ</th>
                  <th>Last Error</th>
                  <th>Events</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {devices.map((device) => (
                  <tr key={device.device_id}>
                    <td>
                      <div>{shortId(device.device_id, 12)}</div>
                      <button
                        className="button subtle"
                        onClick={async () => {
                          const copied = await copyToClipboard(device.device_id);
                          setCopyMessage(copied ? 'device_id copied' : 'Unable to copy device_id');
                          setTimeout(() => setCopyMessage(''), 1200);
                        }}
                      >
                        Copy
                      </button>
                    </td>
                    <td>{new Date(device.last_seen).toLocaleString()}</td>
                    <td>{device.outbox_pending_count ?? 0}</td>
                    <td>{device.dlq_count ?? 0}</td>
                    <td>{device.last_error_summary || '-'}</td>
                    <td>{device.event_count}</td>
                    <td>
                      <Link className="button" href={`/devices/${encodeURIComponent(device.device_id)}?range=${range}`}>
                        Drill-down
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <div>
              Total {total} devices, page {currentPage}/{totalPages}
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <select
                className="input"
                value={limit}
                onChange={(event) => {
                  setLimit(Number(event.target.value));
                  setOffset(0);
                }}
              >
                <option value={25}>25 / page</option>
                <option value={50}>50 / page</option>
                <option value={100}>100 / page</option>
              </select>
              <button className="button" onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset === 0}>
                Prev
              </button>
              <button className="button" onClick={() => setOffset(offset + limit)} disabled={!hasNext}>
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
