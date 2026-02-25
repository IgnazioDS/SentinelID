'use client';

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { adminAPI, Event } from '../../lib/api';
import { copyToClipboard, normalizeRange, rangeStartEpoch, shortId } from '../../lib/time';
import { EmptyState, ErrorState, LoadingState } from '../components/ui-state';

function EventDrawer({ event, onClose }: { event: Event; onClose: () => void }) {
  const [copyMessage, setCopyMessage] = useState<string>('');

  const copyValue = async (label: string, value?: string) => {
    try {
      const copied = await copyToClipboard(value);
      setCopyMessage(copied ? `${label} copied` : `Unable to copy ${label}`);
    } catch {
      setCopyMessage(`Unable to copy ${label}`);
    }
    setTimeout(() => setCopyMessage(''), 1200);
  };

  return (
    <aside className="drawer" role="dialog" aria-label="Event details">
      <div className="drawer-header">
        <h2>Event Detail</h2>
        <button type="button" className="button" onClick={onClose}>Close</button>
      </div>

      <div className="key-value"><span className="key">Event ID</span><span>{event.event_id}</span></div>
      <div className="key-value"><span className="key">Device ID</span><span>{event.device_id}</span></div>
      <div className="key-value"><span className="key">Outcome</span><span>{event.outcome}</span></div>
      <div className="key-value"><span className="key">Reasons</span><span>{event.reason_codes.join(', ') || '-'}</span></div>
      <div className="key-value"><span className="key">Risk</span><span>{event.risk_score ?? '-'}</span></div>
      <div className="key-value"><span className="key">Liveness</span><span>{event.liveness_passed === undefined ? '-' : event.liveness_passed ? 'pass' : 'fail'}</span></div>
      <div className="key-value"><span className="key">Similarity</span><span>{event.similarity_score ?? '-'}</span></div>
      <div className="key-value"><span className="key">Latency (s)</span><span>{event.session_duration_seconds ?? '-'}</span></div>
      <div className="key-value"><span className="key">Timestamp</span><span>{new Date(event.timestamp * 1000).toLocaleString()}</span></div>
      <div className="key-value"><span className="key">Ingested At</span><span>{new Date(event.ingested_at).toLocaleString()}</span></div>

      <div className="section">
        <div className="key-value">
          <span className="key">Request ID</span>
          <span>
            {event.request_id || '-'}
            {event.request_id ? (
              <button className="button subtle" onClick={() => copyValue('request_id', event.request_id)} style={{ marginLeft: 8 }}>
                Copy
              </button>
            ) : null}
          </span>
        </div>
        <div className="key-value">
          <span className="key">Session ID</span>
          <span>
            {event.session_id || '-'}
            {event.session_id ? (
              <button className="button subtle" onClick={() => copyValue('session_id', event.session_id)} style={{ marginLeft: 8 }}>
                Copy
              </button>
            ) : null}
          </span>
        </div>
      </div>

      {copyMessage ? <p className="muted">{copyMessage}</p> : null}
    </aside>
  );
}

export default function EventsPage() {
  const searchParams = useSearchParams();
  const range = normalizeRange(searchParams.get('range'));
  const topSearch = (searchParams.get('q') || '').trim();

  const [events, setEvents] = useState<Event[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [hasNext, setHasNext] = useState(false);

  const [deviceId, setDeviceId] = useState('');
  const [requestId, setRequestId] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [outcome, setOutcome] = useState('');
  const [reasonCode, setReasonCode] = useState('');

  const [appliedFilters, setAppliedFilters] = useState({
    deviceId: '',
    requestId: '',
    sessionId: '',
    outcome: '',
    reasonCode: '',
  });

  const [selectedEvent, setSelectedEvent] = useState<Event | null>(null);

  useEffect(() => {
    setOffset(0);
  }, [range, topSearch]);

  useEffect(() => {
    let mounted = true;

    async function loadEvents() {
      try {
        setLoading(true);
        setError(null);

        const startTs = rangeStartEpoch(range);
        const endTs = Math.floor(Date.now() / 1000);
        const response = await adminAPI.getEvents({
          limit,
          offset,
          device_id: appliedFilters.deviceId || undefined,
          request_id: appliedFilters.requestId || undefined,
          session_id: appliedFilters.sessionId || undefined,
          outcome: appliedFilters.outcome || undefined,
          reason_code: appliedFilters.reasonCode || undefined,
          start_ts: startTs,
          end_ts: endTs,
          q: topSearch || undefined,
        });

        if (!mounted) return;
        setEvents(response.events);
        setTotal(response.total);
        setHasNext(response.has_next);
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : 'Failed to load events');
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    loadEvents();
    return () => {
      mounted = false;
    };
  }, [limit, offset, range, topSearch, appliedFilters]);

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  const activeFilterCount = useMemo(() => {
    return Object.values(appliedFilters).filter((value) => value.trim().length > 0).length;
  }, [appliedFilters]);

  if (loading && events.length === 0) {
    return <LoadingState text="Loading events..." />;
  }

  return (
    <div>
      <h1 className="page-title">Events</h1>
      <p className="page-subtitle">
        Filter telemetry events by correlation IDs, outcome, and reason codes. Window: {range}
      </p>

      <div className="filters">
        <input className="input" placeholder="Device ID" value={deviceId} onChange={(event) => setDeviceId(event.target.value)} />
        <input className="input" placeholder="Request ID" value={requestId} onChange={(event) => setRequestId(event.target.value)} />
        <input className="input" placeholder="Session ID" value={sessionId} onChange={(event) => setSessionId(event.target.value)} />

        <select className="input" value={outcome} onChange={(event) => setOutcome(event.target.value)}>
          <option value="">All outcomes</option>
          <option value="allow">allow</option>
          <option value="deny">deny</option>
          <option value="error">error</option>
        </select>

        <input className="input" placeholder="Reason code" value={reasonCode} onChange={(event) => setReasonCode(event.target.value)} />

        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="button primary"
            onClick={() => {
              setAppliedFilters({
                deviceId: deviceId.trim(),
                requestId: requestId.trim(),
                sessionId: sessionId.trim(),
                outcome,
                reasonCode: reasonCode.trim(),
              });
              setOffset(0);
            }}
          >
            Apply
          </button>
          <button
            className="button"
            onClick={() => {
              setDeviceId('');
              setRequestId('');
              setSessionId('');
              setOutcome('');
              setReasonCode('');
              setAppliedFilters({ deviceId: '', requestId: '', sessionId: '', outcome: '', reasonCode: '' });
              setOffset(0);
            }}
          >
            Clear
          </button>
        </div>
      </div>

      {activeFilterCount > 0 ? <p className="muted">Active filters: {activeFilterCount}</p> : null}

      {error ? (
        <ErrorState message={error} action={<button className="button subtle" onClick={() => window.location.reload()}>Retry</button>} />
      ) : null}

      {!loading && events.length === 0 ? (
        <EmptyState title="No events found" description="Adjust filters or time range and try again." />
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Device</th>
                  <th>Request</th>
                  <th>Session</th>
                  <th>Outcome</th>
                  <th>Reason Codes</th>
                  <th>Risk</th>
                  <th>Liveness</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.event_id} className="row-clickable" onClick={() => setSelectedEvent(event)}>
                    <td>{shortId(event.event_id, 12)}</td>
                    <td>{shortId(event.device_id, 12)}</td>
                    <td>{event.request_id ? shortId(event.request_id, 12) : '-'}</td>
                    <td>{event.session_id ? shortId(event.session_id, 12) : '-'}</td>
                    <td>
                      <span className={`badge ${event.outcome}`}>{event.outcome}</span>
                    </td>
                    <td>{event.reason_codes.slice(0, 2).join(', ') || '-'}</td>
                    <td>{event.risk_score ?? '-'}</td>
                    <td>{event.liveness_passed === undefined ? '-' : event.liveness_passed ? 'pass' : 'fail'}</td>
                    <td>{new Date(event.timestamp * 1000).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <div>
              Total {total} events, page {currentPage}/{totalPages}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
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

      {selectedEvent ? <EventDrawer event={selectedEvent} onClose={() => setSelectedEvent(null)} /> : null}
    </div>
  );
}
