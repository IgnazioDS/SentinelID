'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { TIME_RANGE_OPTIONS, normalizeRange } from '../../lib/time';

const NAV_ITEMS = [
  { href: '/', label: 'Overview' },
  { href: '/events', label: 'Events' },
  { href: '/devices', label: 'Devices' },
  { href: '/support', label: 'Support' },
];
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE !== '0';

function withQuery(path: string, range: string, q: string): string {
  const params = new URLSearchParams();
  params.set('range', range);
  if (q.trim()) {
    params.set('q', q.trim());
  }
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export default function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  const range = normalizeRange(searchParams.get('range'));
  const query = searchParams.get('q') || '';

  const [searchInput, setSearchInput] = useState(query);

  useEffect(() => {
    setSearchInput(query);
  }, [query]);

  const navLinks = useMemo(
    () => NAV_ITEMS.map((item) => ({ ...item, hrefWithQuery: withQuery(item.href, range, query) })),
    [range, query]
  );

  const updateParams = (nextRange: string, nextQ: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('range', nextRange);
    if (nextQ.trim()) {
      params.set('q', nextQ.trim());
    } else {
      params.delete('q');
    }
    router.push(`${pathname}?${params.toString()}`);
  };

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand-wrap">
          <div className="admin-brand">SentinelID Ops</div>
          {DEMO_MODE ? <span className="demo-badge">Demo</span> : null}
        </div>
        <nav>
          {navLinks.map((item) => (
            <Link
              key={item.href}
              href={item.hrefWithQuery}
              className={`nav-link ${
                item.href === '/'
                  ? pathname === '/'
                    ? 'active'
                    : ''
                  : pathname === item.href || pathname.startsWith(`${item.href}/`)
                    ? 'active'
                    : ''
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      <div className="admin-main-wrap">
        <header className="admin-topbar">
          <div className="topbar-group">
            <label htmlFor="time-range" className="topbar-label">
              Time range
            </label>
            <select
              id="time-range"
              value={range}
              onChange={(event) => updateParams(event.target.value, searchInput)}
              className="input"
            >
              {TIME_RANGE_OPTIONS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>

          <form
            className="topbar-search"
            onSubmit={(event) => {
              event.preventDefault();
              updateParams(range, searchInput);
            }}
          >
            <input
              type="search"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Search device/request/session"
              className="input"
            />
            <button type="submit" className="button primary">
              Search
            </button>
          </form>
          {pathname === '/events' ? (
            <span className="topbar-hint">Tip: Use request_id and session_id filters for exact trace lookup.</span>
          ) : null}
        </header>

        <main className="admin-content">{children}</main>
      </div>
    </div>
  );
}
