import { useCallback, useEffect, useMemo, useState } from 'react';
import CameraView, { CameraStatus, DesktopTab } from './features/camera/CameraView';
import apiClient from './lib/apiClient';
import { toUserFacingError } from './lib/apiErrors';
import { TAURI_REQUIRED_MESSAGE, isTauriRuntimeAvailable } from './lib/tauriRuntime';

interface ServiceState {
  status: 'starting' | 'running' | 'stopped';
  error: string | null;
  detail: string | null;
}

function formatLastSync(value: string | null): string {
  if (!value) {
    return 'n/a';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function App() {
  const tauriAvailable = isTauriRuntimeAvailable();
  const [activeTab, setActiveTab] = useState<DesktopTab>('login');
  const [serviceState, setServiceState] = useState<ServiceState>({
    status: tauriAvailable ? 'starting' : 'stopped',
    error: tauriAvailable ? null : TAURI_REQUIRED_MESSAGE,
    detail: null,
  });
  const [cameraStatus, setCameraStatus] = useState<CameraStatus>('loading');
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);
  const [demoMode, setDemoMode] = useState<boolean>(() => {
    if (typeof window === 'undefined') {
      return false;
    }
    return window.localStorage.getItem('sentinelid_demo_mode') === '1';
  });

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('sentinelid_demo_mode', demoMode ? '1' : '0');
    }
  }, [demoMode]);

  const startEdge = useCallback(async () => {
    if (!tauriAvailable) {
      setServiceState({
        status: 'stopped',
        error: TAURI_REQUIRED_MESSAGE,
        detail: null,
      });
      return;
    }

    setServiceState({ status: 'starting', error: null, detail: null });

    try {
      await apiClient.startEdge();
      setServiceState({ status: 'running', error: null, detail: null });
    } catch (error) {
      const message = toUserFacingError(error);
      const detail = error instanceof Error ? error.message : String(error);
      setServiceState({ status: 'stopped', error: message, detail });
    }
  }, [tauriAvailable]);

  useEffect(() => {
    startEdge().catch(() => undefined);

    return () => {
      if (!tauriAvailable) {
        return;
      }
      apiClient.killEdge().catch(() => undefined);
    };
  }, [startEdge, tauriAvailable]);

  useEffect(() => {
    if (!tauriAvailable) {
      return;
    }

    const timer = window.setInterval(async () => {
      try {
        await apiClient.getCurrentEdgeInfo();
        setServiceState((prev) =>
          prev.status === 'running' && !prev.error
            ? prev
            : { status: 'running', error: null, detail: null }
        );
      } catch {
        setServiceState((prev) =>
          prev.status === 'stopped'
            ? prev
            : { status: 'stopped', error: 'Edge service is not running.', detail: prev.detail }
        );
      }
    }, 4000);

    return () => window.clearInterval(timer);
  }, [tauriAvailable]);

  const statusLabel = useMemo(() => {
    if (serviceState.status === 'running') {
      return 'Running';
    }
    if (serviceState.status === 'starting') {
      return 'Starting';
    }
    return 'Stopped';
  }, [serviceState.status]);

  const cameraLabel = useMemo(() => {
    if (cameraStatus === 'ready') return 'Ready';
    if (cameraStatus === 'error') return 'Error';
    return 'Initializing';
  }, [cameraStatus]);

  const serviceStopped = serviceState.status === 'stopped';

  return (
    <div className="desktop-shell">
      <header className="app-header">
        <div>
          <h1>SentinelID Desktop</h1>
          <p>Local biometric verification with clear operator flows.</p>
        </div>
      </header>

      <nav className="tab-nav" aria-label="Primary">
        <button
          className={activeTab === 'login' ? 'tab-btn active' : 'tab-btn'}
          onClick={() => setActiveTab('login')}
        >
          Login
        </button>
        <button
          className={activeTab === 'enroll' ? 'tab-btn active' : 'tab-btn'}
          onClick={() => setActiveTab('enroll')}
        >
          Enroll
        </button>
        <button
          className={activeTab === 'settings' ? 'tab-btn active' : 'tab-btn'}
          onClick={() => setActiveTab('settings')}
        >
          Settings
        </button>
      </nav>

      {serviceState.error && (
        <section className="app-alert" role="alert">
          <strong>{serviceState.error}</strong>
          {demoMode && serviceState.detail && <pre>{serviceState.detail}</pre>}
          {tauriAvailable && (
            <button className="btn-primary" onClick={() => startEdge()}>
              Retry Edge Startup
            </button>
          )}
        </section>
      )}

      <main className="app-main">
        {tauriAvailable ? (
          <CameraView
            activeTab={activeTab}
            edgeReady={serviceState.status === 'running'}
            edgeError={serviceState.error}
            demoMode={demoMode}
            onDemoModeChange={setDemoMode}
            onCameraStatusChange={setCameraStatus}
            onLastSyncChange={setLastSyncAt}
          />
        ) : (
          <section className="not-tauri-card">
            <h2>Desktop Runtime Required</h2>
            <p>{TAURI_REQUIRED_MESSAGE}</p>
            <p>Run this UI from the SentinelID desktop binary to access camera and local Edge APIs.</p>
          </section>
        )}
      </main>

      <footer className="status-strip" aria-live="polite">
        <div className="status-item">
          <span className="status-label">Service</span>
          <span className={`status-pill ${serviceState.status}`}>{statusLabel}</span>
          {serviceStopped && tauriAvailable && (
            <button className="link-btn" onClick={() => startEdge()}>
              Restart
            </button>
          )}
        </div>
        <div className="status-item">
          <span className="status-label">Camera</span>
          <span className={`status-pill ${cameraStatus}`}>{cameraLabel}</span>
        </div>
        <div className="status-item">
          <span className="status-label">Last sync</span>
          <span>{formatLastSync(lastSyncAt)}</span>
        </div>
      </footer>
    </div>
  );
}

export default App;
