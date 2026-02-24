import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import apiClient, { DiagnosticsResponse } from '../../lib/apiClient';
import './CameraView.css';

type Mode = 'verify' | 'enroll';

type AuthState =
  | 'idle'
  | 'starting'
  | 'in_challenge'
  | 'step_up'
  | 'finishing'
  | 'success'
  | 'error';

type EnrollState =
  | 'idle'
  | 'starting'
  | 'capturing'
  | 'committing'
  | 'success'
  | 'error';

interface AuthSession {
  session_id: string;
  challenges: string[];
  current_challenge?: string;
  progress?: string;
  decision?: string;
  reason_codes?: string[];
  risk_reasons?: string[];
  quality_reason_codes?: string[];
  liveness_passed?: boolean;
  similarity_score?: number;
  risk_score?: number;
  step_up?: boolean;
  step_up_challenges?: string[];
  in_step_up?: boolean;
}

interface EnrollSession {
  session_id: string;
  target_frames: number;
  accepted_frames: number;
  reason_codes: string[];
  quality?: Record<string, unknown>;
  template_id?: string;
}

const USER_REASON_MESSAGES: Record<string, string> = {
  NOT_ENROLLED: 'No enrolled face template exists on this device.',
  LIVENESS_FAILED: 'Liveness check failed. Try again with clearer movement.',
  SIMILARITY_BELOW_THRESHOLD: 'Face match confidence is below the threshold.',
  RISK_HIGH: 'Risk score is high. Access denied.',
  RISK_STEP_UP: 'Additional verification is required.',
  MAX_STEP_UPS_REACHED: 'Step-up attempts were exhausted.',
  NO_FACE: 'No face detected. Center your face in the frame.',
  MULTIPLE_FACES: 'Multiple faces detected. Ensure only one face is visible.',
  LOW_QUALITY: 'Frame quality is too low. Improve lighting and steadiness.',
  TOO_DARK: 'Lighting is too dark.',
  TOO_BLURRY: 'Image is blurry. Hold still for a sharper frame.',
  POSE_TOO_LARGE: 'Head angle is too large. Face the camera directly.',
  ENROLL_INCOMPLETE: 'Enrollment needs more high-quality frames before commit.',
  STEP_UP_FAILED: 'Step-up verification failed.',
};

function reasonToUserMessage(reason: string): string {
  return USER_REASON_MESSAGES[reason] ?? reason;
}

function getInstructionForChallenge(challenge?: string): string {
  switch (challenge?.toLowerCase()) {
    case 'blink':
      return 'Blink naturally when prompted.';
    case 'turn_left':
      return 'Turn your head slowly to the left.';
    case 'turn_right':
      return 'Turn your head slowly to the right.';
    default:
      return 'Follow the current on-screen challenge.';
  }
}

function extractProgress(progressText?: string): number | null {
  if (!progressText) return null;
  const match = progressText.match(/(\d+)\s*\/\s*(\d+)/);
  if (!match) return null;
  const done = Number(match[1]);
  const total = Number(match[2]);
  if (!Number.isFinite(done) || !Number.isFinite(total) || total <= 0) return null;
  return Math.min(100, Math.max(0, (done / total) * 100));
}

const CameraView: React.FC = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const frameLoopRef = useRef<number | null>(null);
  const streamingRef = useRef(false);
  const inFlightRef = useRef(false);
  const lastFrameAtRef = useRef(0);
  const streamSessionIdRef = useRef<string | null>(null);

  const [mode, setMode] = useState<Mode>('verify');

  const [authState, setAuthState] = useState<AuthState>('idle');
  const [session, setSession] = useState<AuthSession | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [frameCount, setFrameCount] = useState(0);

  const [enrollState, setEnrollState] = useState<EnrollState>('idle');
  const [enrollSession, setEnrollSession] = useState<EnrollSession | null>(null);
  const [enrollError, setEnrollError] = useState<string | null>(null);
  const [enrollLabel, setEnrollLabel] = useState('default');

  const [demoMode, setDemoMode] = useState(false);
  const [telemetryEnabled, setTelemetryEnabled] = useState(false);
  const [telemetryRuntimeAvailable, setTelemetryRuntimeAvailable] = useState(false);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);

  const [diagnostics, setDiagnostics] = useState<DiagnosticsResponse | null>(null);
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);

  useEffect(() => {
    async function getCamera() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setAuthError('Camera API is not available in this environment.');
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 } },
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      } catch {
        setAuthError('Cannot access camera. Check camera permissions.');
        setEnrollError('Cannot access camera. Check camera permissions.');
      }
    }

    getCamera();

    return () => {
      streamingRef.current = false;
      if (frameLoopRef.current !== null) {
        cancelAnimationFrame(frameLoopRef.current);
      }
      if (videoRef.current?.srcObject) {
        (videoRef.current.srcObject as MediaStream).getTracks().forEach((t) => t.stop());
      }
    };
  }, []);

  const refreshDiagnostics = useCallback(async () => {
    try {
      const [diag, telemetry] = await Promise.all([
        apiClient.getDiagnostics(),
        apiClient.getTelemetrySettings(),
      ]);
      setDiagnostics(diag);
      setTelemetryEnabled(Boolean(telemetry.telemetry_enabled));
      setTelemetryRuntimeAvailable(Boolean(telemetry.runtime_available));
      setDiagnosticsError(null);
    } catch (err) {
      setDiagnosticsError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    refreshDiagnostics();
    const timer = window.setInterval(() => {
      refreshDiagnostics().catch(() => undefined);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [refreshDiagnostics]);

  const captureFrameDataAsync = useCallback(async (): Promise<string | null> => {
    if (!videoRef.current) return null;
    if (videoRef.current.videoWidth === 0 || videoRef.current.videoHeight === 0) return null;

    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob((value) => resolve(value), 'image/jpeg', 0.85)
    );
    if (!blob) return null;
    return await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(String(reader.result));
      reader.readAsDataURL(blob);
    });
  }, []);

  const stopVerifyStream = useCallback(() => {
    streamingRef.current = false;
    streamSessionIdRef.current = null;
    if (frameLoopRef.current !== null) {
      cancelAnimationFrame(frameLoopRef.current);
      frameLoopRef.current = null;
    }
    inFlightRef.current = false;
  }, []);

  const startVerifyStream = useCallback(
    (sessionId: string) => {
      stopVerifyStream();
      streamingRef.current = true;
      streamSessionIdRef.current = sessionId;
      lastFrameAtRef.current = 0;

      const step = async (now: number) => {
        if (!streamingRef.current || streamSessionIdRef.current !== sessionId) return;

        const elapsed = now - lastFrameAtRef.current;
        if (elapsed < 100 || inFlightRef.current) {
          frameLoopRef.current = requestAnimationFrame(step);
          return;
        }

        inFlightRef.current = true;
        try {
          const frameData = await captureFrameDataAsync();
          if (!frameData) {
            frameLoopRef.current = requestAnimationFrame(step);
            return;
          }

          const result = await apiClient.authFrame(sessionId, frameData);
          setFrameCount((c) => c + 1);
          setSession((prev) =>
            prev
              ? {
                  ...prev,
                  current_challenge: result.current_challenge,
                  progress: result.progress,
                  in_step_up: result.in_step_up,
                  quality_reason_codes: result.quality_reason_codes ?? [],
                }
              : null
          );
          lastFrameAtRef.current = now;
        } catch (err) {
          setAuthError(err instanceof Error ? err.message : String(err));
          setAuthState('error');
          stopVerifyStream();
        } finally {
          inFlightRef.current = false;
          if (streamingRef.current) {
            frameLoopRef.current = requestAnimationFrame(step);
          }
        }
      };

      frameLoopRef.current = requestAnimationFrame(step);
    },
    [captureFrameDataAsync, stopVerifyStream]
  );

  const startAuth = async () => {
    try {
      setAuthState('starting');
      setAuthError(null);
      setFrameCount(0);
      const data = await apiClient.startAuth();
      const newSession: AuthSession = {
        session_id: data.session_id,
        challenges: data.challenges,
        current_challenge: data.challenges?.[0],
      };
      setSession(newSession);
      setAuthState('in_challenge');
      startVerifyStream(data.session_id);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : String(err));
      setAuthState('error');
    }
  };

  const finishAuth = async () => {
    try {
      if (!session) return;
      stopVerifyStream();
      setAuthState('finishing');
      const data = await apiClient.finishAuth(session.session_id);

      if (data.step_up && data.decision === 'step_up') {
        const firstStepUpChallenge = (data.step_up_challenges ?? [])[0];
        setSession((prev) =>
          prev
            ? {
                ...prev,
                step_up: true,
                step_up_challenges: data.step_up_challenges ?? [],
                current_challenge: firstStepUpChallenge,
                risk_score: data.risk_score,
                reason_codes: data.reason_codes,
                risk_reasons: data.risk_reasons ?? [],
                similarity_score: data.similarity_score,
                quality_reason_codes: data.quality_reason_codes ?? [],
                in_step_up: true,
              }
            : null
        );
        setAuthState('step_up');
        startVerifyStream(session.session_id);
        return;
      }

      setSession((prev) => (prev ? { ...prev, ...data } : null));
      setAuthState(data.decision === 'allow' ? 'success' : 'error');
      await refreshDiagnostics();
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : String(err));
      setAuthState('error');
    }
  };

  const resetAuth = () => {
    stopVerifyStream();
    setAuthState('idle');
    setSession(null);
    setAuthError(null);
    setFrameCount(0);
  };

  const startEnrollment = async () => {
    try {
      setEnrollState('starting');
      setEnrollError(null);
      const data = await apiClient.startEnroll();
      setEnrollSession({
        session_id: data.session_id,
        target_frames: data.target_frames,
        accepted_frames: 0,
        reason_codes: [],
      });
      setEnrollState('capturing');
    } catch (err) {
      setEnrollError(err instanceof Error ? err.message : String(err));
      setEnrollState('error');
    }
  };

  const captureEnrollFrame = async () => {
    try {
      if (!enrollSession) return;
      const frameData = await captureFrameDataAsync();
      if (!frameData) throw new Error('Unable to capture frame');
      const data = await apiClient.enrollFrame(enrollSession.session_id, frameData);
      setEnrollSession((prev) =>
        prev
          ? {
              ...prev,
              accepted_frames: data.accepted_frames,
              target_frames: data.target_frames,
              reason_codes: data.reason_codes ?? [],
              quality: data.quality ?? {},
            }
          : null
      );
    } catch (err) {
      setEnrollError(err instanceof Error ? err.message : String(err));
      setEnrollState('error');
    }
  };

  const commitEnrollment = async () => {
    try {
      if (!enrollSession) return;
      setEnrollState('committing');
      const data = await apiClient.commitEnroll(enrollSession.session_id, enrollLabel || 'default');
      setEnrollSession((prev) =>
        prev
          ? {
              ...prev,
              template_id: data.template_id,
              accepted_frames: data.accepted_frames,
              target_frames: data.target_frames,
              reason_codes: [],
            }
          : null
      );
      setEnrollState('success');
      await refreshDiagnostics();
    } catch (err) {
      setEnrollError(err instanceof Error ? err.message : String(err));
      setEnrollState('error');
    }
  };

  const resetEnrollment = async () => {
    try {
      if (enrollSession) {
        await apiClient.resetEnroll(enrollSession.session_id);
      }
    } catch {
      // UI reset should proceed even if API reset fails.
    } finally {
      setEnrollSession(null);
      setEnrollState('idle');
      setEnrollError(null);
    }
  };

  const updateTelemetryEnabled = async (enabled: boolean) => {
    try {
      setSettingsBusy(true);
      setSettingsMessage(null);
      const response = await apiClient.updateTelemetrySettings(enabled);
      setTelemetryEnabled(Boolean(response.telemetry_enabled));
      await refreshDiagnostics();
      setSettingsMessage(enabled ? 'Telemetry enabled.' : 'Telemetry disabled.');
    } catch (err) {
      setSettingsMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setSettingsBusy(false);
    }
  };

  const resetIdentity = async () => {
    const confirmReset = window.confirm(
      'Reset local identity data? This removes enrolled templates, audit history, and queued telemetry.'
    );
    if (!confirmReset) return;
    try {
      setSettingsBusy(true);
      setSettingsMessage(null);
      await apiClient.deleteIdentity();
      resetAuth();
      await resetEnrollment();
      await refreshDiagnostics();
      setSettingsMessage('Identity reset completed.');
    } catch (err) {
      setSettingsMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setSettingsBusy(false);
    }
  };

  const verifyProgress = useMemo(() => extractProgress(session?.progress), [session?.progress]);
  const enrollProgress = useMemo(() => {
    if (!enrollSession || enrollSession.target_frames <= 0) return 0;
    return Math.min(100, (enrollSession.accepted_frames / enrollSession.target_frames) * 100);
  }, [enrollSession]);

  const friendlyAuthReasons = useMemo(
    () => (session?.reason_codes ?? []).map(reasonToUserMessage),
    [session?.reason_codes]
  );
  const friendlyQualityReasons = useMemo(
    () => (session?.quality_reason_codes ?? []).map(reasonToUserMessage),
    [session?.quality_reason_codes]
  );
  const friendlyEnrollReasons = useMemo(
    () => (enrollSession?.reason_codes ?? []).map(reasonToUserMessage),
    [enrollSession?.reason_codes]
  );

  const renderProgressBar = (value: number | null) => {
    if (value === null) return null;
    return (
      <div className="progress-bar-wrap" aria-hidden="true">
        <div className="progress-bar-fill" style={{ width: `${value.toFixed(0)}%` }} />
      </div>
    );
  };

  const renderVerifyDemoBadge = () => {
    if (!demoMode || !session) return null;
    const parts: string[] = [];
    if (session.risk_score !== undefined) parts.push(`risk ${session.risk_score.toFixed(3)}`);
    if (session.similarity_score !== undefined) parts.push(`sim ${session.similarity_score.toFixed(3)}`);
    if (session.risk_reasons && session.risk_reasons.length > 0) parts.push(session.risk_reasons.join(', '));
    if (session.in_step_up) parts.push('step-up active');
    if (parts.length === 0) return null;
    return (
      <div className="demo-badge">
        <strong>Demo:</strong> {parts.join(' | ')}
      </div>
    );
  };

  const renderVerifyContent = () => {
    switch (authState) {
      case 'idle':
        return (
          <div className="camera-controls">
            <h2>Verification</h2>
            <p>Start a live verification session.</p>
            <button onClick={startAuth} className="btn-primary">
              Start Verification
            </button>
          </div>
        );
      case 'starting':
        return (
          <div className="camera-status">
            <p>Starting verification session...</p>
          </div>
        );
      case 'in_challenge':
      case 'step_up':
        return (
          <div className="camera-challenge">
            <h3>{authState === 'step_up' ? 'Step-up Verification' : 'Liveness Challenge'}</h3>
            <p className="instruction">{getInstructionForChallenge(session?.current_challenge)}</p>
            <p className="progress">Progress: {session?.progress}</p>
            {renderProgressBar(verifyProgress)}
            <p className="frame-count">Frames sent: {frameCount}</p>
            {friendlyQualityReasons.length > 0 && (
              <p className="quality-warning">Quality: {friendlyQualityReasons.join(' | ')}</p>
            )}
            {renderVerifyDemoBadge()}
            <div className="button-group">
              <button onClick={finishAuth} className="btn-secondary">
                {authState === 'step_up' ? 'Complete Step-up' : 'Finish Verification'}
              </button>
              <button onClick={resetAuth} className="btn-secondary">
                Cancel
              </button>
            </div>
          </div>
        );
      case 'finishing':
        return (
          <div className="camera-status">
            <p>Finalizing decision...</p>
          </div>
        );
      case 'success':
      case 'error':
        return (
          <div className={`camera-result ${authState === 'success' ? 'success' : 'error'}`}>
            <h3>{authState === 'success' ? 'Verification Successful' : 'Verification Failed'}</h3>
            {authError && <p>{authError}</p>}
            <p>Decision: {session?.decision ?? '-'}</p>
            <p>Liveness: {session?.liveness_passed ? 'passed' : 'failed'}</p>
            {session?.similarity_score !== undefined && <p>Similarity: {session.similarity_score.toFixed(3)}</p>}
            {session?.risk_score !== undefined && <p>Risk score: {session.risk_score.toFixed(3)}</p>}
            {friendlyAuthReasons.length > 0 && <p>Reasons: {friendlyAuthReasons.join(' | ')}</p>}
            <button onClick={resetAuth} className="btn-primary">
              Retry
            </button>
          </div>
        );
      default:
        return null;
    }
  };

  const renderEnrollContent = () => {
    switch (enrollState) {
      case 'idle':
        return (
          <div className="camera-controls">
            <h2>Enrollment</h2>
            <p>Capture high-quality frames. Raw frames are never stored.</p>
            <div className="field-row">
              <label>Label</label>
              <input value={enrollLabel} onChange={(e) => setEnrollLabel(e.target.value)} />
            </div>
            <button onClick={startEnrollment} className="btn-primary">
              Start Enrollment
            </button>
          </div>
        );
      case 'starting':
        return (
          <div className="camera-status">
            <p>Starting enrollment session...</p>
          </div>
        );
      case 'capturing':
        return (
          <div className="camera-challenge">
            <h3>Capture Enrollment Frames</h3>
            <p className="progress">
              Progress: {enrollSession?.accepted_frames ?? 0}/{enrollSession?.target_frames ?? 0}
            </p>
            {renderProgressBar(enrollProgress)}
            {friendlyEnrollReasons.length > 0 && (
              <p className="quality-warning">Quality: {friendlyEnrollReasons.join(' | ')}</p>
            )}
            <div className="button-group">
              <button onClick={captureEnrollFrame} className="btn-secondary">
                Capture Frame
              </button>
              <button
                onClick={commitEnrollment}
                className="btn-primary"
                disabled={(enrollSession?.accepted_frames ?? 0) < (enrollSession?.target_frames ?? 0)}
              >
                Commit Enrollment
              </button>
              <button onClick={resetEnrollment} className="btn-secondary">
                Reset
              </button>
            </div>
          </div>
        );
      case 'committing':
        return (
          <div className="camera-status">
            <p>Committing encrypted template...</p>
          </div>
        );
      case 'success':
        return (
          <div className="camera-result success">
            <h3>Enrollment Complete</h3>
            <p>Template ID: {enrollSession?.template_id}</p>
            <p>
              Frames: {enrollSession?.accepted_frames}/{enrollSession?.target_frames}
            </p>
            <button onClick={resetEnrollment} className="btn-primary">
              Enroll Again
            </button>
          </div>
        );
      case 'error':
        return (
          <div className="camera-result error">
            <h3>Enrollment Failed</h3>
            <p>{enrollError ?? 'Unknown enrollment error'}</p>
            <button onClick={() => setEnrollState('capturing')} className="btn-secondary">
              Retry Capture
            </button>
            <button onClick={resetEnrollment} className="btn-primary">
              Reset Session
            </button>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="camera-view">
      <div className="mode-toggle">
        <button className={mode === 'verify' ? 'btn-primary' : 'btn-secondary'} onClick={() => setMode('verify')}>
          Verification
        </button>
        <button className={mode === 'enroll' ? 'btn-primary' : 'btn-secondary'} onClick={() => setMode('enroll')}>
          Enrollment
        </button>
      </div>

      <video ref={videoRef} autoPlay playsInline width="640" height="480" className="camera-feed" />
      <div className="camera-overlay">{mode === 'verify' ? renderVerifyContent() : renderEnrollContent()}</div>

      <div className="settings-panel">
        <h3>Settings</h3>
        <div className="settings-row">
          <label>
            <input type="checkbox" checked={demoMode} onChange={(e) => setDemoMode(e.target.checked)} />
            Demo Mode (local-only visualization)
          </label>
        </div>
        <div className="settings-row">
          <label>
            <input
              type="checkbox"
              checked={telemetryEnabled}
              disabled={!telemetryRuntimeAvailable || settingsBusy}
              onChange={(e) => updateTelemetryEnabled(e.target.checked)}
            />
            Telemetry enabled
          </label>
          {!telemetryRuntimeAvailable && <span className="settings-note">Runtime unavailable</span>}
        </div>
        <div className="settings-row">
          <button className="btn-secondary" disabled={settingsBusy} onClick={resetIdentity}>
            Reset Identity
          </button>
          <button className="btn-secondary" disabled={settingsBusy} onClick={() => refreshDiagnostics()}>
            Refresh Diagnostics
          </button>
        </div>
        {settingsMessage && <div className="settings-note">{settingsMessage}</div>}
        {diagnosticsError && <div className="settings-note settings-error">{diagnosticsError}</div>}

        <div className="diagnostics">
          <p>
            Device fingerprint: <code>{diagnostics?.device_key_fingerprint ?? 'n/a'}</code>
          </p>
          <p>
            Last export status:{' '}
            {diagnostics?.telemetry?.last_export_error
              ? `error (${diagnostics.telemetry.last_export_error})`
              : diagnostics?.telemetry?.last_export_attempt_time
              ? `ok (${diagnostics.telemetry.last_export_attempt_time})`
              : 'n/a'}
          </p>
          <p>
            Frame processing: p50{' '}
            {diagnostics?.performance?.['frame.decode']?.p50_ms ?? 'n/a'} ms, p95{' '}
            {diagnostics?.performance?.['frame.decode']?.p95_ms ?? 'n/a'} ms
          </p>
        </div>
      </div>
    </div>
  );
};

export default CameraView;

