'use client';

import { useSearchParams } from 'next/navigation';
import { useState } from 'react';
import { adminAPI } from '../../lib/api';
import { normalizeRange } from '../../lib/time';
import { ErrorState } from '../components/ui-state';

export default function SupportPage() {
  const searchParams = useSearchParams();
  const range = normalizeRange(searchParams.get('range'));

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastGeneratedAt, setLastGeneratedAt] = useState<string | null>(null);
  const [lastFile, setLastFile] = useState<string | null>(null);

  const downloadBundle = async () => {
    try {
      setBusy(true);
      setError(null);
      const result = await adminAPI.generateSupportBundle({ window: range, events_limit: 150 });

      const href = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = href;
      link.download = result.filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(href);

      setLastGeneratedAt(result.createdAt ?? new Date().toISOString());
      setLastFile(result.filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate support bundle');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 className="page-title">Support Bundle</h1>
      <p className="page-subtitle">
        Generate a sanitized diagnostics bundle for operators. Includes stats, recent events, and environment summary.
      </p>

      <div className="card" style={{ maxWidth: 760 }}>
        <p>
          Current range: <strong>{range}</strong>
        </p>
        <p className="muted">No frames, embeddings, tokens, or signatures are included in this bundle.</p>

        <button className="button primary" onClick={downloadBundle} disabled={busy}>
          {busy ? 'Generating...' : 'Generate support bundle'}
        </button>

        {lastGeneratedAt ? (
          <p className="muted" style={{ marginTop: 12 }}>
            Last generated: {new Date(lastGeneratedAt).toLocaleString()} {lastFile ? `(${lastFile})` : ''}
          </p>
        ) : null}
      </div>

      {error ? <ErrorState message={error} /> : null}
    </div>
  );
}
