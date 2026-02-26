'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextTarget = useMemo(() => searchParams.get('next') || '/', [searchParams]);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function probeSession() {
      const response = await fetch('/api/admin/session/me', { cache: 'no-store' });
      if (!mounted || response.status !== 200) return;
      router.replace(nextTarget);
    }
    probeSession();
    return () => {
      mounted = false;
    };
  }, [router, nextTarget]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const response = await fetch('/api/admin/session/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail || 'Login failed');
      }
      router.replace(nextTarget);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <section className="card" style={{ width: '100%', maxWidth: 420 }}>
        <h1 className="page-title" style={{ marginBottom: 8 }}>
          SentinelID Admin Login
        </h1>
        <p className="page-subtitle">Sign in to access operations dashboards and support tools.</p>

        <form onSubmit={onSubmit} style={{ display: 'grid', gap: 12, marginTop: 16 }}>
          <input
            className="input"
            placeholder="Username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            required
          />
          <input
            className="input"
            type="password"
            placeholder="Password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
          <button className="button primary" type="submit" disabled={busy}>
            {busy ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        {error ? (
          <p className="muted" style={{ color: '#9d0208', marginTop: 12 }}>
            {error}
          </p>
        ) : null}
      </section>
    </main>
  );
}
