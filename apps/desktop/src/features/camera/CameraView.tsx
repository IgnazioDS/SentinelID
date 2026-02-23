import React, { useCallback, useEffect, useRef, useState } from 'react';
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

function getEdgeBaseUrl(): string {
  return (window as any).__edgeInfo?.base_url ?? 'http://127.0.0.1:8000';
}

function getEdgeToken(): string {
  return (window as any).__edgeInfo?.token ?? '';
}

function edgeHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${getEdgeToken()}`,
  };
}

function getInstructionForChallenge(challenge?: string): string {
  switch (challenge?.toLowerCase()) {
    case 'blink':
      return 'Please blink your eyes naturally.';
    case 'turn_left':
      return 'Please turn your head slowly to the left.';
    case 'turn_right':
      return 'Please turn your head slowly to the right.';
    default:
      return 'Please follow the on-screen instructions.';
  }
}

const CameraView: React.FC = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const frameIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const [mode, setMode] = useState<Mode>('verify');

  const [authState, setAuthState] = useState<AuthState>('idle');
  const [session, setSession] = useState<AuthSession | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [frameCount, setFrameCount] = useState(0);
  const [demoMode, setDemoMode] = useState(false);

  const [enrollState, setEnrollState] = useState<EnrollState>('idle');
  const [enrollSession, setEnrollSession] = useState<EnrollSession | null>(null);
  const [enrollError, setEnrollError] = useState<string | null>(null);
  const [enrollLabel, setEnrollLabel] = useState('default');

  useEffect(() => {
    async function getCamera() {
      if (navigator.mediaDevices?.getUserMedia) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 640 }, height: { ideal: 480 } },
          });
          if (videoRef.current) {
            videoRef.current.srcObject = stream;
          }
        } catch {
          setAuthError('Cannot access camera');
          setEnrollError('Cannot access camera');
        }
      }
    }
    getCamera();
    return () => {
      if (videoRef.current?.srcObject) {
        (videoRef.current.srcObject as MediaStream).getTracks().forEach((t) => t.stop());
      }
      if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
    };
  }, []);

  const captureFrameData = useCallback((): string | null => {
    if (!videoRef.current) return null;
    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg');
  }, []);

  const stopFrameCapture = () => {
    if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current);
      frameIntervalRef.current = null;
    }
  };

  const captureAndSendVerifyFrame = useCallback(async () => {
    if (!session) return;
    const frameData = captureFrameData();
    if (!frameData) return;

    try {
      const res = await fetch(`${getEdgeBaseUrl()}/api/v1/auth/frame`, {
        method: 'POST',
        headers: edgeHeaders(),
        body: JSON.stringify({
          session_id: session.session_id,
          frame: frameData,
        }),
      });
      if (!res.ok) throw new Error(`Frame error: ${res.statusText}`);
      const result = await res.json();
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
    } catch (err) {
      setAuthError(String(err));
      setAuthState('error');
      stopFrameCapture();
    }
  }, [captureFrameData, session]);

  const startFrameCapture = useCallback(() => {
    if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
    frameIntervalRef.current = setInterval(captureAndSendVerifyFrame, 125);
  }, [captureAndSendVerifyFrame]);

  const startAuth = async () => {
    try {
      setAuthState('starting');
      setAuthError(null);
      setFrameCount(0);
      const res = await fetch(`${getEdgeBaseUrl()}/api/v1/auth/start`, {
        method: 'POST',
        headers: edgeHeaders(),
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(`Start failed: ${res.statusText}`);
      const data = await res.json();
      setSession({
        session_id: data.session_id,
        challenges: data.challenges,
        current_challenge: data.challenges[0],
      });
      setAuthState('in_challenge');
      startFrameCapture();
    } catch (err) {
      setAuthError(String(err));
      setAuthState('error');
    }
  };

  const finishAuth = async () => {
    try {
      if (!session) return;
      setAuthState('finishing');
      stopFrameCapture();
      const res = await fetch(`${getEdgeBaseUrl()}/api/v1/auth/finish`, {
        method: 'POST',
        headers: edgeHeaders(),
        body: JSON.stringify({ session_id: session.session_id }),
      });
      if (!res.ok) throw new Error(`Finish failed: ${res.statusText}`);
      const data = await res.json();

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
        startFrameCapture();
        return;
      }

      setSession((prev) => (prev ? { ...prev, ...data } : null));
      setAuthState(data.decision === 'allow' ? 'success' : 'error');
    } catch (err) {
      setAuthError(String(err));
      setAuthState('error');
    }
  };

  const resetAuth = () => {
    stopFrameCapture();
    setAuthState('idle');
    setSession(null);
    setAuthError(null);
    setFrameCount(0);
  };

  const startEnrollment = async () => {
    try {
      setEnrollState('starting');
      setEnrollError(null);
      const res = await fetch(`${getEdgeBaseUrl()}/api/v1/enroll/start`, {
        method: 'POST',
        headers: edgeHeaders(),
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(`Enroll start failed: ${res.statusText}`);
      const data = await res.json();
      setEnrollSession({
        session_id: data.session_id,
        target_frames: data.target_frames,
        accepted_frames: 0,
        reason_codes: [],
      });
      setEnrollState('capturing');
    } catch (err) {
      setEnrollError(String(err));
      setEnrollState('error');
    }
  };

  const captureEnrollFrame = async () => {
    try {
      if (!enrollSession) return;
      const frameData = captureFrameData();
      if (!frameData) throw new Error('Unable to capture frame');
      const res = await fetch(`${getEdgeBaseUrl()}/api/v1/enroll/frame`, {
        method: 'POST',
        headers: edgeHeaders(),
        body: JSON.stringify({
          session_id: enrollSession.session_id,
          frame: frameData,
        }),
      });
      if (!res.ok) throw new Error(`Enroll frame failed: ${res.statusText}`);
      const data = await res.json();
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
      setEnrollError(String(err));
      setEnrollState('error');
    }
  };

  const commitEnrollment = async () => {
    try {
      if (!enrollSession) return;
      setEnrollState('committing');
      const res = await fetch(`${getEdgeBaseUrl()}/api/v1/enroll/commit`, {
        method: 'POST',
        headers: edgeHeaders(),
        body: JSON.stringify({
          session_id: enrollSession.session_id,
          label: enrollLabel || 'default',
        }),
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`Enroll commit failed: ${body}`);
      }
      const data = await res.json();
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
    } catch (err) {
      setEnrollError(String(err));
      setEnrollState('error');
    }
  };

  const resetEnrollment = async () => {
    try {
      if (enrollSession) {
        await fetch(`${getEdgeBaseUrl()}/api/v1/enroll/reset`, {
          method: 'POST',
          headers: edgeHeaders(),
          body: JSON.stringify({ session_id: enrollSession.session_id }),
        });
      }
    } catch {
      // ignore reset errors in UI cleanup
    } finally {
      setEnrollSession(null);
      setEnrollState('idle');
      setEnrollError(null);
    }
  };

  const renderVerifyDemoBadge = () => {
    if (!demoMode || !session) return null;
    const parts: string[] = [];
    if (session.risk_score !== undefined) parts.push(`risk: ${session.risk_score.toFixed(3)}`);
    if (session.similarity_score !== undefined)
      parts.push(`similarity: ${session.similarity_score.toFixed(3)}`);
    if (session.risk_reasons && session.risk_reasons.length > 0)
      parts.push(session.risk_reasons.join(', '));
    if (session.in_step_up) parts.push('step-up active');
    if (parts.length === 0) return null;
    return (
      <div className="demo-badge">
        <strong>Demo</strong> | {parts.join(' | ')}
      </div>
    );
  };

  const renderVerifyContent = () => {
    switch (authState) {
      case 'idle':
        return (
          <div className="camera-controls">
            <h2>Verification</h2>
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
            <h3>
              {authState === 'step_up' ? 'Additional Verification Required' : `Challenge: ${session?.current_challenge?.toUpperCase()}`}
            </h3>
            <p className="instruction">{getInstructionForChallenge(session?.current_challenge)}</p>
            <p className="progress">Progress: {session?.progress}</p>
            <p className="frame-count">Frames sent: {frameCount}</p>
            {session?.quality_reason_codes && session.quality_reason_codes.length > 0 && (
              <p className="quality-warning">Quality: {session.quality_reason_codes.join(', ')}</p>
            )}
            {renderVerifyDemoBadge()}
            <div className="button-group">
              <button onClick={finishAuth} className="btn-secondary">
                {authState === 'step_up' ? 'Complete Step-up' : 'Finish Verification'}
              </button>
            </div>
          </div>
        );
      case 'finishing':
        return (
          <div className="camera-status">
            <p>Processing verification result...</p>
          </div>
        );
      case 'success':
      case 'error':
        return (
          <div className={`camera-result ${authState === 'success' ? 'success' : 'error'}`}>
            <h3>{authState === 'success' ? 'Verification Successful' : 'Verification Failed'}</h3>
            {authState === 'error' && <p>{authError ?? 'Unknown error occurred'}</p>}
            <p>Decision: {session?.decision}</p>
            <p>Liveness Passed: {session?.liveness_passed ? 'Yes' : 'No'}</p>
            {session?.similarity_score !== undefined && (
              <p>Similarity: {session.similarity_score.toFixed(3)}</p>
            )}
            {session?.reason_codes && <p>Reasons: {session.reason_codes.join(', ')}</p>}
            {session?.quality_reason_codes && session.quality_reason_codes.length > 0 && (
              <p>Quality: {session.quality_reason_codes.join(', ')}</p>
            )}
            <button onClick={resetAuth} className="btn-primary">
              Try Again
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
            <p>Capture high-quality samples. No raw frames are stored.</p>
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
            {enrollSession?.reason_codes && enrollSession.reason_codes.length > 0 && (
              <p className="quality-warning">Quality: {enrollSession.reason_codes.join(', ')}</p>
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
            <p>Committing enrolled template...</p>
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
            <p>{enrollError ?? 'Unknown error occurred'}</p>
            <button onClick={resetEnrollment} className="btn-primary">
              Retry
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
        <button
          className={mode === 'verify' ? 'btn-primary' : 'btn-secondary'}
          onClick={() => setMode('verify')}
        >
          Verification
        </button>
        <button
          className={mode === 'enroll' ? 'btn-primary' : 'btn-secondary'}
          onClick={() => setMode('enroll')}
        >
          Enrollment
        </button>
      </div>
      {mode === 'verify' && (
        <div className="demo-toggle">
          <label>
            <input type="checkbox" checked={demoMode} onChange={(e) => setDemoMode(e.target.checked)} /> Demo mode
            (local only)
          </label>
        </div>
      )}
      <video ref={videoRef} autoPlay playsInline width="640" height="480" className="camera-feed" />
      <div className="camera-overlay">{mode === 'verify' ? renderVerifyContent() : renderEnrollContent()}</div>
    </div>
  );
};

export default CameraView;
