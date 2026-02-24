'use client';

import { useEffect, useState } from 'react';
import { adminAPI, Device } from '../../lib/api';
import Link from 'next/link';

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [hasNext, setHasNext] = useState(false);

  useEffect(() => {
    async function loadDevices() {
      try {
        setLoading(true);
        setError(null);
        const response = await adminAPI.getDevices({
          limit,
          offset,
        });
        setDevices(response.devices);
        setTotal(response.total);
        setHasNext(response.has_next);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load devices');
      } finally {
        setLoading(false);
      }
    }

    loadDevices();
  }, [limit, offset]);

  const handlePreviousPage = () => {
    setOffset(Math.max(0, offset - limit));
  };

  const handleNextPage = () => {
    if (hasNext) {
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
        <Link href="/events" style={{ marginRight: '20px' }}>
          Events
        </Link>
        <Link href="/stats">Stats</Link>
      </div>

      <h1>Registered Devices</h1>

      <div style={{ marginBottom: '20px' }}>
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
        <p>Loading devices...</p>
      ) : (
        <>
          <div style={{ marginBottom: '10px' }}>
            Total: {total} devices (Page {currentPage}/{totalPages})
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
                    Device ID
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Status
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Last Seen
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Registered
                  </th>
                  <th style={{ padding: '10px', textAlign: 'left', border: '1px solid #ddd' }}>
                    Events
                  </th>
                </tr>
              </thead>
              <tbody>
                {devices.map((device) => (
                  <tr key={device.device_id}>
                    <td style={{ padding: '10px', border: '1px solid #ddd', fontSize: '12px' }}>
                      {device.device_id}
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd' }}>
                      <span
                        style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          backgroundColor: device.is_active ? '#d4edda' : '#f8d7da',
                          color: device.is_active ? '#155724' : '#721c24',
                        }}
                      >
                        {device.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', fontSize: '12px' }}>
                      {new Date(device.last_seen).toLocaleString()}
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', fontSize: '12px' }}>
                      {new Date(device.registered_at).toLocaleString()}
                    </td>
                    <td style={{ padding: '10px', border: '1px solid #ddd', textAlign: 'center' }}>
                      {device.event_count}
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
              disabled={!hasNext}
              style={{
                padding: '8px 16px',
                backgroundColor: !hasNext ? '#ccc' : '#007bff',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: !hasNext ? 'default' : 'pointer',
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
