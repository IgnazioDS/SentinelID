import React, { useRef, useEffect, useState, useCallback } from 'react';
import apiClient from '../../lib/apiClient';
import './CameraView.css';

type AuthState = 'idle' | 'starting' | 'in_challenge' | 'finishing' | 'success' | 'error';

interface AuthSession {
  session_id: string;
  challenges: string[];
  current_challenge?: string;
  progress?: string;
  decision?: string;
  reason_codes?: string[];
  error?: string;
}

interface EdgeInfo {
  base_url: string;
  token: string;
}

const CameraView: React.FC = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const frameIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // UI State
  const [authState, setAuthState] = useState<AuthState>('idle');
  const [session, setSession] = useState<AuthSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [frameCount, setFrameCount] = useState(0);

  // Get camera stream
  useEffect(() => {
    async function getCamera() {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 640 }, height: { ideal: 480 } }
          });
          if (videoRef.current) {
            videoRef.current.srcObject = stream;
          }
        } catch (error) {
          console.error("Error accessing the camera: ", error);
          setError("Cannot access camera");
        }
      }
    }

    getCamera();

    return () => {
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach(track => track.stop());
      }
      if (frameIntervalRef.current) {
        clearInterval(frameIntervalRef.current);
      }
    };
  }, []);

  // Capture frame from video and send to edge
  const captureAndSendFrame = useCallback(async () => {
    if (!videoRef.current || !session) return;

    try {
      const canvas = document.createElement('canvas');
      canvas.width = videoRef.current.videoWidth;
      canvas.height = videoRef.current.videoHeight;
      const context = canvas.getContext('2d');

      if (!context) return;

      context.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
      const frameData = canvas.toDataURL('image/jpeg');

      // Send frame to edge auth endpoint
      const response = await fetch(
        `${(window as any).__edgeInfo?.base_url || 'http://127.0.0.1:8000'}/api/v1/auth/frame`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${(window as any).__edgeInfo?.token || ''}`,
          },
          body: JSON.stringify({
            session_id: session.session_id,
            frame: frameData,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`Frame processing failed: ${response.statusText}`);
      }

      const frameResult = await response.json();
      setFrameCount(fc => fc + 1);

      // Update session with progress
      setSession(prev => prev ? {
        ...prev,
        current_challenge: frameResult.current_challenge,
        progress: frameResult.progress,
      } : null);

      console.log('Frame processed:', frameResult);
    } catch (err) {
      console.error('Error sending frame:', err);
      setError(String(err));
    }
  }, [session]);

  // Start authentication session
  const startAuth = async () => {
    try {
      setAuthState('starting');
      setError(null);
      setFrameCount(0);

      // Start session on edge
      const response = await fetch(
        `${(window as any).__edgeInfo?.base_url || 'http://127.0.0.1:8000'}/api/v1/auth/start`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${(window as any).__edgeInfo?.token || ''}`,
          },
          body: JSON.stringify({}),
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to start auth: ${response.statusText}`);
      }

      const startResult = await response.json();
      setSession({
        session_id: startResult.session_id,
        challenges: startResult.challenges,
        current_challenge: startResult.challenges[0],
      });

      setAuthState('in_challenge');

      // Start frame capture loop (8 fps)
      if (frameIntervalRef.current) {
        clearInterval(frameIntervalRef.current);
      }
      frameIntervalRef.current = setInterval(captureAndSendFrame, 125); // 1000ms / 8 = 125ms
    } catch (err) {
      console.error('Error starting auth:', err);
      setError(String(err));
      setAuthState('error');
    }
  };

  // Finish authentication
  const finishAuth = async () => {
    try {
      if (!session) return;

      setAuthState('finishing');

      // Stop frame capture
      if (frameIntervalRef.current) {
        clearInterval(frameIntervalRef.current);
        frameIntervalRef.current = null;
      }

      // Call finish endpoint
      const response = await fetch(
        `${(window as any).__edgeInfo?.base_url || 'http://127.0.0.1:8000'}/api/v1/auth/finish`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${(window as any).__edgeInfo?.token || ''}`,
          },
          body: JSON.stringify({
            session_id: session.session_id,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to finish auth: ${response.statusText}`);
      }

      const finishResult = await response.json();
      setSession(prev => prev ? { ...prev, ...finishResult } : null);
      setAuthState(finishResult.decision === 'allow' ? 'success' : 'error');
    } catch (err) {
      console.error('Error finishing auth:', err);
      setError(String(err));
      setAuthState('error');
    }
  };

  // Reset to idle state
  const reset = () => {
    if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current);
      frameIntervalRef.current = null;
    }
    setAuthState('idle');
    setSession(null);
    setError(null);
    setFrameCount(0);
  };

  // Render based on state
  const renderContent = () => {
    switch (authState) {
      case 'idle':
        return (
          <div className="camera-controls">
            <h2>Liveness Authentication</h2>
            <button onClick={startAuth} className="btn-primary">Start Authentication</button>
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
            <div className="button-group">
              <button onClick={finishAuth} className="btn-secondary">Finish Authentication</button>
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
            <h3>✓ Authentication Successful</h3>
            <p>Decision: {session?.decision}</p>
            <p>Liveness Passed: {session?.liveness_passed ? 'Yes' : 'No'}</p>
            {session?.reason_codes && (
              <p>Reason: {session.reason_codes.join(', ')}</p>
            )}
            <button onClick={reset} className="btn-primary">Try Again</button>
          </div>
        );

      case 'error':
        return (
          <div className="camera-result error">
            <h3>✗ Authentication Failed</h3>
            <p>{error || 'Unknown error occurred'}</p>
            {session?.reason_codes && (
              <p>Reason: {session.reason_codes.join(', ')}</p>
            )}
            <button onClick={reset} className="btn-primary">Try Again</button>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="camera-view">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        width="640"
        height="480"
        className="camera-feed"
      />
      <div className="camera-overlay">
        {renderContent()}
      </div>
    </div>
  );
};

function getInstructionForChallenge(challenge?: string): string {
  switch (challenge?.toLowerCase()) {
    case 'blink':
      return 'Please blink your eyes naturally. Wait for the prompt and blink once or twice.';
    case 'turn_left':
      return 'Please turn your head slowly to the left.';
    case 'turn_right':
      return 'Please turn your head slowly to the right.';
    default:
      return 'Please follow the on-screen instructions.';
  }
}

export default CameraView;
