'use client';

import { useEffect, useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { adminAPI, EventSeriesResponse, StatsResponse } from '../lib/api';
import { normalizeRange } from '../lib/time';
import { useSearchParams } from 'next/navigation';
import { EmptyState, ErrorState, LoadingState } from './components/ui-state';

function formatBucketLabel(value: string) {
  const dt = new Date(value);
  return `${dt.getMonth() + 1}/${dt.getDate()} ${dt.getHours().toString().padStart(2, '0')}:00`;
}

export default function OverviewPage() {
  const searchParams = useSearchParams();
  const range = normalizeRange(searchParams.get('range'));

  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [series, setSeries] = useState<EventSeriesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [statsData, seriesData] = await Promise.all([
          adminAPI.getStats(range),
          adminAPI.getEventSeries({ window: range }),
        ]);
        if (!mounted) return;
        setStats(statsData);
        setSeries(seriesData);
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, [range]);

  const outcomeData = useMemo(() => {
    if (!series) return [];
    return [
      { name: 'ALLOW', value: series.outcome_breakdown.allow },
      { name: 'DENY', value: series.outcome_breakdown.deny },
      { name: 'ERROR', value: series.outcome_breakdown.error },
    ];
  }, [series]);

  if (loading) {
    return <LoadingState text="Loading overview..." />;
  }

  if (error) {
    return <ErrorState message={error} action={<button className="button subtle" onClick={() => window.location.reload()}>Retry</button>} />;
  }

  if (!stats || !series) {
    return <EmptyState title="No overview data" description="No telemetry has been ingested yet." />;
  }

  const hasChartData = series.points.some((point) => point.events > 0);

  return (
    <div>
      <h1 className="page-title">Operations Overview</h1>
      <p className="page-subtitle">Window: {range}</p>

      <div className="card-grid">
        <div className="card">
          <p className="metric-label">Events Ingested (window)</p>
          <p className="metric-value">{stats.events_ingested_count}</p>
        </div>
        <div className="card">
          <p className="metric-label">Ingest Failures (window)</p>
          <p className="metric-value">{stats.ingest_fail_count}</p>
        </div>
        <div className="card">
          <p className="metric-label">Active Devices (window)</p>
          <p className="metric-value">{stats.active_devices_window}</p>
        </div>
        <div className="card">
          <p className="metric-label">DLQ Total</p>
          <p className="metric-value">{stats.dlq_total}</p>
        </div>
      </div>

      <section className="section">
        <h2>Events Over Time</h2>
        {hasChartData ? (
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series.points}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="bucket_start" tickFormatter={formatBucketLabel} minTickGap={32} />
                <YAxis />
                <Tooltip labelFormatter={formatBucketLabel} />
                <Legend />
                <Line type="monotone" dataKey="events" stroke="#0466c8" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyState title="No events in selected window" description="Adjust the time range or wait for telemetry ingest." />
        )}
      </section>

      <section className="section">
        <h2>Outcome Breakdown</h2>
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={outcomeData}
                dataKey="value"
                nameKey="name"
                outerRadius={110}
                label
              >
                <Cell fill="#2a9d8f" />
                <Cell fill="#c1121f" />
                <Cell fill="#f4a261" />
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="section">
        <h2>Exporter Lag Trend</h2>
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={series.points}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="bucket_start" tickFormatter={formatBucketLabel} minTickGap={32} />
              <YAxis />
              <Tooltip labelFormatter={formatBucketLabel} />
              <Legend />
              <Bar dataKey="outbox_pending_avg" fill="#f4a261" name="Outbox Pending Avg" />
              <Bar dataKey="dlq_avg" fill="#c1121f" name="DLQ Avg" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
