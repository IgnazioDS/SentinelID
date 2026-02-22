'use client';

import { useEffect, useState } from 'react';
import { adminAPI, Event, EventsResponse } from '@/lib/api';
import Link from 'next/link';

export default function EventsPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [deviceFilter, setDeviceFilter] = useState('');
  const [outcomeFilter, setOutcomeFilter] = useState<string>('');

  useEffect(() => {
    async function loadEvents() {
      try {
        setLoading(true);
        setError(null);
        const response = await adminAPI.getEvents({
          limit,
          offset,
          device_id: deviceFilter || undefined,
          outcome: outcomeFilter || undefined,
        });
        setEvents(response.events);
        setTotal(response.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load events');
      } finally {
        setLoading(false);
      }
    }

    loadEvents();
  }, [limit, offset, deviceFilter, outcomeFilter]);

  const handlePreviousPage = () => {
    setOffset(Math.max(0, offset - limit));
  };

  const handleNextPage = () => {
    if (offset + limit < total) {
      setOffset(offset + limit);
    }
  };

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  return (
    <div style={{ padding: '20px' }}>
      <div style={{ marginBottom: '20px' }}>
        <Link href="/" style={{ marginRight: '20px' }}>
          Home
        </Link>
        <Link href="/stats" style={{ marginRight: '20px' }}>
          Stats
        </Link>
        <Link href="/devices">Devices</Link>
      </div>

      <h1>Telemetry Events</h1>

      <div
        style={{
          marginBottom: '20px',
          display: 'flex',
          gap: '10px',
          flexWrap: 'wrap',
        }}
      >
        <input
          type="text"
          placeholder="Filter by device ID..."
          value={deviceFilter}
          onChange={(e) => {
            setDeviceFilter(e.target.value);
            setOffset(0);
          }}
          style={{ padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }}
        />

        <select
          value={outcomeFilter}
          onChange={(e) => {
            setOutcomeFilter(e.target.value);
            setOffset(0);
          }}
          style={{ padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }}
        >
          <option value="">All Outcomes</option>
          <option value="allow">Allow</option>
          <option value="deny">Deny</option>
          <option value="error">Error</option>
        </select>

        <select
          value={limit}
          onChange={(e) => {
            setLimit(Number(e.target.value));
            setOffset(0);
          }}
          style={{ padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }}
        >
          <option value={25}>25 per page</option>
          <option value={50}>50 per page</option>
          <option value={100}>100 per page</option>
        </select>
      </div>

      {error && (
        <div style={{ color: 'red', marginBottom: '20px', padding: '10px', backgroundColor: '#ffe0e0', borderRadius: '4px' }}>
          {error}
        </div>
      )}

      {loading ? (
        <p>Loading events...</p>
      ) : (
        <>
          <div style={{ marginBottom: '10px' }}>
            Total: {total} events (Page {currentPage}/{totalPages})
          </div>

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
                    Event ID
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Device ID
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Outcome
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Liveness
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Timestamp
                  </th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.event_id}>
                    <td style={{ padding: '10px', border: '1px solid #ddd', fontSize: '12px' }}>
                      {event.event_id.substring(0, 8)}...
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', fontSize: '12px' }}>
                      {event.device_id.substring(0, 8)}...
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd' }}>
                      <span
                        style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          backgroundColor:
                            event.outcome === 'allow'
                              ? '#d4edda'
                              : event.outcome === 'deny'
                                ? '#f8d7da'
                                : '#e2e3e5',
                          color:
                            event.outcome === 'allow'
                              ? '#155724'
                              : event.outcome === 'deny'
                                ? '#721c24'
                                : '#383d41',
                        }}
                      >
                        {event.outcome}
                      </span>
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd' }}>
                      {event.liveness_passed === true ? '✓' : event.liveness_passed === false ? '✗' : '-'}
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', fontSize: '12px' }}>
                      {new Date(event.timestamp * 1000).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ display: 'flex', gap: '10px', justifyContent: 'space-between' }}>
            <button
              onClick={handlePreviousPage}
              disabled={offset === 0}
              style={{
                padding: '8px 16px',
                backgroundColor: offset === 0 ? '#ccc' : '#007bff',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: offset === 0 ? 'default' : 'pointer',
              }}
            >
              Previous
            </button>
            <span>
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={handleNextPage}
              disabled={offset + limit >= total}
              style={{
                padding: '8px 16px',
                backgroundColor: offset + limit >= total ? '#ccc' : '#007bff',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: offset + limit >= total ? 'default' : 'pointer',
              }}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
