import React, { useRef, useEffect, useState, useCallback } from 'react';
import './CameraView.css';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type AuthState =
  | 'idle'
  | 'starting'
  | 'in_challenge'
  | 'step_up'
  | 'finishing'
  | 'success'
  | 'error';

interface AuthSession {
  session_id: string;
  challenges: string[];
  current_challenge?: string;
  progress?: string;
  decision?: string;
  reason_codes?: string[];
  liveness_passed?: boolean;
  risk_score?: number;
  step_up?: boolean;
  step_up_challenges?: string[];
  in_step_up?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const CameraView: React.FC = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const frameIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const [authState, setAuthState] = useState<AuthState>('idle');
  const [session, setSession] = useState<AuthSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [frameCount, setFrameCount] = useState(0);
  // Demo mode: local-only toggle; shows risk score and reason codes.
  // Does not store or transmit any additional data.
  const [demoMode, setDemoMode] = useState(false);

  // Camera stream setup
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
          setError('Cannot access camera');
        }
      }
    }
    getCamera();
    return () => {
      if (videoRef.current?.srcObject) {
        (videoRef.current.srcObject as MediaStream)
          .getTracks()
          .forEach((t) => t.stop());
      }
      if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
    };
  }, []);

  // -------------------------------------------------------------------------
  // Frame capture loop
  // -------------------------------------------------------------------------

  const captureAndSendFrame = useCallback(async () => {
    if (!videoRef.current || !session) return;

    try {
      const canvas = document.createElement('canvas');
      canvas.width = videoRef.current.videoWidth;
      canvas.height = videoRef.current.videoHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
      const frameData = canvas.toDataURL('image/jpeg');

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
            }
          : null
      );
    } catch (err) {
      setError(String(err));
    }
  }, [session]);

  const startFrameCapture = useCallback(() => {
    if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
    frameIntervalRef.current = setInterval(captureAndSendFrame, 125); // ~8 fps
  }, [captureAndSendFrame]);

  const stopFrameCapture = () => {
    if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current);
      frameIntervalRef.current = null;
    }
  };

  // -------------------------------------------------------------------------
  // Auth flow
  // -------------------------------------------------------------------------

  const startAuth = async () => {
    try {
      setAuthState('starting');
      setError(null);
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
      setError(String(err));
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

      // Step-up required: server issued additional challenges
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
                in_step_up: true,
              }
            : null
        );
        setAuthState('step_up');
        // Resume frame capture for step-up challenge evaluation
        startFrameCapture();
        return;
      }

      // Final decision (allow or deny)
      setSession((prev) => (prev ? { ...prev, ...data } : null));
      setAuthState(data.decision === 'allow' ? 'success' : 'error');
    } catch (err) {
      setError(String(err));
      setAuthState('error');
    }
  };

  const reset = () => {
    stopFrameCapture();
    setAuthState('idle');
    setSession(null);
    setError(null);
    setFrameCount(0);
  };

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  const renderDemoBadge = () => {
    if (!demoMode || !session) return null;
    const parts: string[] = [];
    if (session.risk_score !== undefined)
      parts.push(`risk: ${session.risk_score.toFixed(3)}`);
    if (session.reason_codes && session.reason_codes.length > 0)
      parts.push(session.reason_codes.join(', '));
    if (session.in_step_up) parts.push('step-up active');
    if (parts.length === 0) return null;
    return (
      <div className="demo-badge">
        <strong>Demo</strong> | {parts.join(' | ')}
      </div>
    );
  };

  const renderContent = () => {
    switch (authState) {
      case 'idle':
        return (
          <div className="camera-controls">
            <h2>Liveness Authentication</h2>
            <button onClick={startAuth} className="btn-primary">
              Start Authentication
            </button>
          </div>
        );

      case 'starting':
        return (
          <div className="camera-status">
            <p>Starting authentication session...</p>
          </div>
        );

      case 'in_challenge':
        return (
          <div className="camera-challenge">
            <h3>Challenge: {session?.current_challenge?.toUpperCase()}</h3>
            <p className="instruction">
              {getInstructionForChallenge(session?.current_challenge)}
            </p>
            <p className="progress">Progress: {session?.progress}</p>
            <p className="frame-count">Frames sent: {frameCount}</p>
            {renderDemoBadge()}
            <div className="button-group">
              <button onClick={finishAuth} className="btn-secondary">
                Finish Authentication
              </button>
            </div>
          </div>
        );

      case 'step_up':
        return (
          <div className="camera-challenge step-up">
            <h3>Additional Verification Required</h3>
            <p className="step-up-notice">
              Your session requires an extra verification step. Please complete
              the challenge below.
            </p>
            <h4>Challenge: {session?.current_challenge?.toUpperCase()}</h4>
            <p className="instruction">
              {getInstructionForChallenge(session?.current_challenge)}
            </p>
            <p className="progress">Progress: {session?.progress}</p>
            <p className="frame-count">Frames sent: {frameCount}</p>
            {renderDemoBadge()}
            <div className="button-group">
              <button onClick={finishAuth} className="btn-secondary">
                Complete Verification
              </button>
            </div>
          </div>
        );

      case 'finishing':
        return (
          <div className="camera-status">
            <p>Processing results...</p>
          </div>
        );

      case 'success':
        return (
          <div className="camera-result success">
            <h3>Authentication Successful</h3>
            <p>Decision: {session?.decision}</p>
            <p>Liveness Passed: {session?.liveness_passed ? 'Yes' : 'No'}</p>
            {session?.reason_codes && (
              <p>Reason: {session.reason_codes.join(', ')}</p>
            )}
            {demoMode && session?.risk_score !== undefined && (
              <p className="demo-info">
                Risk Score: {session.risk_score.toFixed(3)}
              </p>
            )}
            <button onClick={reset} className="btn-primary">
              Try Again
            </button>
          </div>
        );

      case 'error':
        return (
          <div className="camera-result error">
            <h3>Authentication Failed</h3>
            <p>{error ?? 'Unknown error occurred'}</p>
            {session?.reason_codes && (
              <p>Reason: {session.reason_codes.join(', ')}</p>
            )}
            {demoMode && session?.risk_score !== undefined && (
              <p className="demo-info">
                Risk Score: {session.risk_score.toFixed(3)}
              </p>
            )}
            <button onClick={reset} className="btn-primary">
              Try Again
            </button>
          </div>
        );

      default:
        return null;
    }
  };

  // -------------------------------------------------------------------------
  // Root render
  // -------------------------------------------------------------------------

  return (
    <div className="camera-view">
      <div className="demo-toggle">
        <label>
          <input
            type="checkbox"
            checked={demoMode}
            onChange={(e) => setDemoMode(e.target.checked)}
          />
          {' '}Demo mode (local only)
        </label>
      </div>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        width="640"
        height="480"
        className="camera-feed"
      />
      <div className="camera-overlay">{renderContent()}</div>
    </div>
  );
};

export default CameraView;
