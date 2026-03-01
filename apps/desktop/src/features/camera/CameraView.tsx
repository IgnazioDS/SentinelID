import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import apiClient, { DiagnosticsResponse } from '../../lib/apiClient';
import { ApiClientError, toUserFacingError } from '../../lib/apiErrors';
import { recoveryHint } from '../../lib/errorHints';
import { enrollmentPercent, extractProgressParts } from '../../lib/progress';
import { reasonCodesToMessages, summarizeDecision } from '../../lib/reasonMessages';
import {
  AuthState,
  EnrollState,
  assertStateMachineRecoveryCoverage,
  canRetryAuth,
  canRetryEnroll,
} from '../../lib/stateMachine';
import './CameraView.css';

export type DesktopTab = 'login' | 'enroll' | 'settings';
export type CameraStatus = 'loading' | 'ready' | 'error';

interface CameraViewProps {
  activeTab: DesktopTab;
  edgeReady: boolean;
  edgeError: string | null;
  demoMode: boolean;
  onDemoModeChange: (enabled: boolean) => void;
  onCameraStatusChange: (status: CameraStatus) => void;
  onLastSyncChange: (lastSync: string | null) => void;
}

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
  similarity_score?: number | null;
  risk_score?: number | null;
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

function getInstructionForChallenge(challenge?: string): string {
  switch (challenge?.toLowerCase()) {
    case 'blink':
      return 'Blink naturally when prompted.';
    case 'turn_left':
      return 'Turn your head slowly to the left.';
    case 'turn_right':
      return 'Turn your head slowly to the right.';
    default:
      return 'Follow the on-screen challenge prompt.';
  }
}

function qualityFeedback(reasonCodes: string[] | undefined): string {
  const messages = reasonCodesToMessages(reasonCodes ?? []);
  if (messages.length === 0) {
    return 'Quality looks good.';
  }
  return messages.join(' | ');
}

function cameraErrorMessage(error: unknown): string {
  if (error instanceof DOMException) {
    switch (error.name) {
      case 'NotAllowedError':
      case 'PermissionDeniedError':
        return 'Camera permission is blocked. Allow camera access in system settings and retry.';
      case 'NotFoundError':
      case 'DevicesNotFoundError':
        return 'No camera device was found. Connect a camera and retry.';
      case 'NotReadableError':
      case 'TrackStartError':
        return 'Camera is currently in use by another app. Close other camera apps and retry.';
      case 'OverconstrainedError':
        return 'Camera does not support required constraints. Retry with default camera settings.';
      default:
        return `Camera error (${error.name}). Retry after checking camera permissions.`;
    }
  }
  if (error instanceof Error) {
    return `Camera initialization failed: ${error.message}`;
  }
  return 'Camera initialization failed due to an unknown error.';
}

type LegacyGetUserMedia = (
  constraints: MediaStreamConstraints,
  successCallback: (stream: MediaStream) => void,
  errorCallback: (error: unknown) => void
) => void;

function legacyGetUserMediaApi(): LegacyGetUserMedia | null {
  const legacyNavigator = navigator as Navigator & {
    getUserMedia?: LegacyGetUserMedia;
    webkitGetUserMedia?: LegacyGetUserMedia;
    mozGetUserMedia?: LegacyGetUserMedia;
    msGetUserMedia?: LegacyGetUserMedia;
  };

  return (
    legacyNavigator.getUserMedia ??
    legacyNavigator.webkitGetUserMedia ??
    legacyNavigator.mozGetUserMedia ??
    legacyNavigator.msGetUserMedia ??
    null
  );
}

async function requestCameraStream(constraints: MediaStreamConstraints): Promise<MediaStream> {
  if (navigator.mediaDevices?.getUserMedia) {
    return await navigator.mediaDevices.getUserMedia(constraints);
  }

  const legacyApi = legacyGetUserMediaApi();
  if (!legacyApi) {
    throw new Error('No camera capture API is available.');
  }

  return await new Promise<MediaStream>((resolve, reject) => {
    legacyApi.call(navigator, constraints, resolve, reject);
  });
}

function cameraApiUnavailableMessage(): string {
  const legacyNavigator = navigator as Navigator & {
    webkitGetUserMedia?: LegacyGetUserMedia;
    mozGetUserMedia?: LegacyGetUserMedia;
    msGetUserMedia?: LegacyGetUserMedia;
  };
  const secure = typeof window !== 'undefined' ? window.isSecureContext : false;
  const mediaDevicesApi = Boolean(navigator.mediaDevices?.getUserMedia);
  const legacyApi = Boolean(
    legacyNavigator.webkitGetUserMedia ||
      legacyNavigator.mozGetUserMedia ||
      legacyNavigator.msGetUserMedia
  );
  return `Camera API is unavailable in this environment (secureContext=${secure}, mediaDevices=${mediaDevicesApi}, legacyApi=${legacyApi}).`;
}

const CameraView: React.FC<CameraViewProps> = ({
  activeTab,
  edgeReady,
  edgeError,
  demoMode,
  onDemoModeChange,
  onCameraStatusChange,
  onLastSyncChange,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const frameLoopRef = useRef<number | null>(null);
  const streamingRef = useRef(false);
  const inFlightRef = useRef(false);
  const lastFrameAtRef = useRef(0);
  const streamSessionIdRef = useRef<string | null>(null);
  const stepUpTimerRef = useRef<number | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);

  const [authState, setAuthState] = useState<AuthState>('idle');
  const [session, setSession] = useState<AuthSession | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authHint, setAuthHint] = useState<string | null>(null);
  const [authReasonMessages, setAuthReasonMessages] = useState<string[]>([]);
  const [frameCount, setFrameCount] = useState(0);

  const [enrollState, setEnrollState] = useState<EnrollState>('idle');
  const [enrollSession, setEnrollSession] = useState<EnrollSession | null>(null);
  const [enrollError, setEnrollError] = useState<string | null>(null);
  const [enrollHint, setEnrollHint] = useState<string | null>(null);
  const [enrollReasonMessages, setEnrollReasonMessages] = useState<string[]>([]);
  const [enrollLabel, setEnrollLabel] = useState('default');

  const [telemetryEnabled, setTelemetryEnabled] = useState(false);
  const [telemetryRuntimeAvailable, setTelemetryRuntimeAvailable] = useState(false);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [supportMessage, setSupportMessage] = useState<string | null>(null);

  const [diagnostics, setDiagnostics] = useState<DiagnosticsResponse | null>(null);
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);
  const [cameraIssue, setCameraIssue] = useState<string | null>(null);

  const initializeCamera = useCallback(async () => {
    onCameraStatusChange('loading');
    setCameraIssue(null);

    if (!navigator.mediaDevices?.getUserMedia && !legacyGetUserMediaApi()) {
      const message = cameraApiUnavailableMessage();
      setCameraIssue(message);
      setAuthError(message);
      setEnrollError(message);
      onCameraStatusChange('error');
      return;
    }

    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
    }

    try {
      if (navigator.mediaDevices.enumerateDevices) {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const hasVideoInput = devices.some((device) => device.kind === 'videoinput');
        if (!hasVideoInput) {
          const message = 'No camera device was found. Connect a camera and retry.';
          setCameraIssue(message);
          setAuthError(message);
          setEnrollError(message);
          onCameraStatusChange('error');
          return;
        }
      }

      let stream: MediaStream;
      try {
        stream = await requestCameraStream({
          video: { width: { ideal: 640 }, height: { ideal: 480 } },
        });
      } catch {
        // Fallback for cameras that reject explicit constraints.
        stream = await requestCameraStream({ video: true });
      }
      cameraStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      onCameraStatusChange('ready');
      setAuthError(null);
      setEnrollError(null);
    } catch (error) {
      const message = cameraErrorMessage(error);
      setCameraIssue(message);
      setAuthError(message);
      setEnrollError(message);
      onCameraStatusChange('error');
    }
  }, [onCameraStatusChange]);

  useEffect(() => {
    assertStateMachineRecoveryCoverage();
  }, []);

  useEffect(() => {
    initializeCamera().catch(() => undefined);

    return () => {
      streamingRef.current = false;
      if (stepUpTimerRef.current !== null) {
        window.clearTimeout(stepUpTimerRef.current);
      }
      if (frameLoopRef.current !== null) {
        cancelAnimationFrame(frameLoopRef.current);
      }
      if (cameraStreamRef.current) {
        cameraStreamRef.current.getTracks().forEach((track) => track.stop());
        cameraStreamRef.current = null;
      }
    };
  }, [initializeCamera]);

  const refreshDiagnostics = useCallback(async () => {
    if (!edgeReady) {
      return;
    }
    try {
      const [diag, telemetry] = await Promise.all([
        apiClient.getDiagnostics(),
        apiClient.getTelemetrySettings(),
      ]);
      setDiagnostics(diag);
      setTelemetryEnabled(Boolean(telemetry.telemetry_enabled));
      setTelemetryRuntimeAvailable(Boolean(telemetry.runtime_available));
      setDiagnosticsError(null);
      const syncTime =
        diag.last_success ??
        diag.telemetry?.last_export_success_time ??
        diag.telemetry?.last_export_attempt_time ??
        null;
      onLastSyncChange(syncTime);
    } catch (error) {
      setDiagnosticsError(
        `Telemetry degraded: ${toUserFacingError(error)} Local authentication remains available.`
      );
    }
  }, [edgeReady, onLastSyncChange]);

  useEffect(() => {
    refreshDiagnostics().catch(() => undefined);
    if (!edgeReady) {
      return;
    }
    const timer = window.setInterval(() => {
      refreshDiagnostics().catch(() => undefined);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [edgeReady, refreshDiagnostics]);

  const captureFrameDataAsync = useCallback(async (): Promise<string | null> => {
    if (!videoRef.current || videoRef.current.videoWidth === 0 || videoRef.current.videoHeight === 0) {
      return null;
    }

    const sourceWidth = videoRef.current.videoWidth;
    const sourceHeight = videoRef.current.videoHeight;
    const maxWidth = 640;
    const maxHeight = 480;
    const scale = Math.min(maxWidth / sourceWidth, maxHeight / sourceHeight, 1);
    const targetWidth = Math.max(1, Math.round(sourceWidth * scale));
    const targetHeight = Math.max(1, Math.round(sourceHeight * scale));

    const canvas = document.createElement('canvas');
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    const context = canvas.getContext('2d');
    if (!context) return null;

    context.drawImage(videoRef.current, 0, 0, targetWidth, targetHeight);

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob((value) => resolve(value), 'image/jpeg', 0.72)
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

      const tick = async (now: number) => {
        if (!streamingRef.current || streamSessionIdRef.current !== sessionId) {
          return;
        }

        const elapsed = now - lastFrameAtRef.current;
        if (elapsed < 100 || inFlightRef.current) {
          frameLoopRef.current = requestAnimationFrame(tick);
          return;
        }

        inFlightRef.current = true;
        try {
          const frameData = await captureFrameDataAsync();
          if (!frameData) {
            frameLoopRef.current = requestAnimationFrame(tick);
            return;
          }

          const result = await apiClient.authFrame(sessionId, frameData);
          setFrameCount((value) => value + 1);
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
          const progress = extractProgressParts(result.progress);
          if (progress && progress.done >= progress.total) {
            // Challenge sequence complete; pause streaming until operator finishes the check.
            stopVerifyStream();
          }
          lastFrameAtRef.current = now;
        } catch (error) {
          setAuthError(toUserFacingError(error));
          setAuthHint(recoveryHint(error));
          if (error instanceof ApiClientError) {
            setAuthReasonMessages(reasonCodesToMessages(error.reasonCodes));
          }
          setAuthState('error');
          stopVerifyStream();
        } finally {
          inFlightRef.current = false;
          if (streamingRef.current) {
            frameLoopRef.current = requestAnimationFrame(tick);
          }
        }
      };

      frameLoopRef.current = requestAnimationFrame(tick);
    },
    [captureFrameDataAsync, stopVerifyStream]
  );

  const resetAuth = useCallback(() => {
    stopVerifyStream();
    if (stepUpTimerRef.current !== null) {
      window.clearTimeout(stepUpTimerRef.current);
      stepUpTimerRef.current = null;
    }
    setAuthState('idle');
    setSession(null);
    setAuthError(null);
    setAuthHint(null);
    setAuthReasonMessages([]);
    setFrameCount(0);
  }, [stopVerifyStream]);

  const continueStepUp = useCallback(() => {
    if (!session) {
      return;
    }
    if (stepUpTimerRef.current !== null) {
      window.clearTimeout(stepUpTimerRef.current);
      stepUpTimerRef.current = null;
    }
    setAuthState('step_up');
    startVerifyStream(session.session_id);
  }, [session, startVerifyStream]);

  const startAuth = async () => {
    if (!edgeReady) {
      setAuthError('Edge service is unavailable. Restart Edge and retry.');
      setAuthState('error');
      return;
    }
    if (cameraIssue) {
      setAuthError(cameraIssue);
      setAuthHint('Retry camera access before starting login.');
      setAuthState('error');
      return;
    }

    try {
      setAuthState('starting');
      setAuthError(null);
      setAuthHint(null);
      setAuthReasonMessages([]);
      setFrameCount(0);

      const data = await apiClient.startAuth();
      setSession({
        session_id: data.session_id,
        challenges: data.challenges,
        current_challenge: data.challenges?.[0],
      });
      setAuthState('in_challenge');
      startVerifyStream(data.session_id);
    } catch (error) {
      setAuthError(toUserFacingError(error));
      setAuthHint(recoveryHint(error));
      if (error instanceof ApiClientError) {
        setAuthReasonMessages(reasonCodesToMessages(error.reasonCodes));
      }
      setAuthState('error');
    }
  };

  const finishAuth = async () => {
    if (!session) {
      return;
    }

    try {
      stopVerifyStream();
      setAuthState('finishing');
      const result = await apiClient.finishAuth(session.session_id);

      if (result.step_up && result.decision === 'step_up') {
        const firstChallenge = (result.step_up_challenges ?? [])[0];
        setSession((prev) =>
          prev
            ? {
                ...prev,
                step_up: true,
                step_up_challenges: result.step_up_challenges ?? [],
                current_challenge: firstChallenge,
                risk_score: result.risk_score,
                reason_codes: result.reason_codes,
                risk_reasons: result.risk_reasons ?? [],
                similarity_score: result.similarity_score,
                quality_reason_codes: result.quality_reason_codes ?? [],
                in_step_up: true,
              }
            : null
        );
        setAuthState('step_up_notice');
        stepUpTimerRef.current = window.setTimeout(() => {
          setAuthState('step_up');
          startVerifyStream(session.session_id);
          stepUpTimerRef.current = null;
        }, 1200);
        return;
      }

      setSession((prev) => (prev ? { ...prev, ...result } : null));
      setAuthReasonMessages(reasonCodesToMessages(result.reason_codes ?? []));
      setAuthState(result.decision === 'allow' ? 'success' : 'error');
      await refreshDiagnostics();
    } catch (error) {
      setAuthError(toUserFacingError(error));
      setAuthHint(recoveryHint(error));
      if (error instanceof ApiClientError) {
        setAuthReasonMessages(reasonCodesToMessages(error.reasonCodes));
      }
      setAuthState('error');
    }
  };

  const startEnrollment = async () => {
    if (!edgeReady) {
      setEnrollError('Edge service is unavailable. Restart Edge and retry.');
      setEnrollState('error');
      return;
    }
    if (cameraIssue) {
      setEnrollError(cameraIssue);
      setEnrollHint('Retry camera access before starting enrollment.');
      setEnrollState('error');
      return;
    }

    try {
      setEnrollState('starting');
      setEnrollError(null);
      setEnrollHint(null);
      setEnrollReasonMessages([]);
      const data = await apiClient.startEnroll();
      setEnrollSession({
        session_id: data.session_id,
        target_frames: data.target_frames,
        accepted_frames: 0,
        reason_codes: [],
      });
      setEnrollState('capturing');
    } catch (error) {
      setEnrollError(toUserFacingError(error));
      setEnrollHint(recoveryHint(error));
      if (error instanceof ApiClientError) {
        setEnrollReasonMessages(reasonCodesToMessages(error.reasonCodes));
      }
      setEnrollState('error');
    }
  };

  const captureEnrollFrame = async () => {
    if (!enrollSession) {
      return;
    }
    if (cameraIssue) {
      setEnrollError(cameraIssue);
      setEnrollHint('Retry camera access and capture again.');
      setEnrollState('error');
      return;
    }

    try {
      const frameData = await captureFrameDataAsync();
      if (!frameData) {
        throw new Error('Unable to capture frame from camera.');
      }
      const result = await apiClient.enrollFrame(enrollSession.session_id, frameData);
      setEnrollSession((prev) =>
        prev
          ? {
              ...prev,
              accepted_frames: result.accepted_frames,
              target_frames: result.target_frames,
              reason_codes: result.reason_codes ?? [],
              quality: result.quality ?? {},
            }
          : null
      );
      setEnrollReasonMessages(reasonCodesToMessages(result.reason_codes ?? []));
      setEnrollError(null);
    } catch (error) {
      setEnrollError(toUserFacingError(error));
      setEnrollHint(recoveryHint(error));
      if (error instanceof ApiClientError) {
        setEnrollReasonMessages(reasonCodesToMessages(error.reasonCodes));
      }
      setEnrollState('error');
    }
  };

  const commitEnrollment = async () => {
    if (!enrollSession) {
      return;
    }

    try {
      setEnrollState('committing');
      const result = await apiClient.commitEnroll(enrollSession.session_id, enrollLabel || 'default');
      setEnrollSession((prev) =>
        prev
          ? {
              ...prev,
              template_id: result.template_id,
              accepted_frames: result.accepted_frames,
              target_frames: result.target_frames,
              reason_codes: [],
            }
          : null
      );
      setEnrollState('success');
      await refreshDiagnostics();
    } catch (error) {
      setEnrollError(toUserFacingError(error));
      setEnrollHint(recoveryHint(error));
      if (error instanceof ApiClientError) {
        setEnrollReasonMessages(reasonCodesToMessages(error.reasonCodes));
      }
      setEnrollState('error');
    }
  };

  const resetEnrollment = useCallback(async () => {
    try {
      if (enrollSession) {
        await apiClient.resetEnroll(enrollSession.session_id);
      }
    } catch {
      // Continue with local reset even if API reset fails.
    } finally {
      setEnrollSession(null);
      setEnrollState('idle');
      setEnrollError(null);
      setEnrollHint(null);
      setEnrollReasonMessages([]);
    }
  }, [enrollSession]);

  const updateTelemetryEnabled = async (enabled: boolean) => {
    try {
      setSettingsBusy(true);
      setSettingsMessage(null);
      const response = await apiClient.updateTelemetrySettings(enabled);
      setTelemetryEnabled(Boolean(response.telemetry_enabled));
      await refreshDiagnostics();
      setSettingsMessage(enabled ? 'Telemetry enabled.' : 'Telemetry disabled.');
    } catch (error) {
      setSettingsMessage(toUserFacingError(error));
    } finally {
      setSettingsBusy(false);
    }
  };

  const resetIdentity = async () => {
    const confirmed = window.confirm(
      'Reset identity data? This removes enrolled templates, local audit history, and queued telemetry.'
    );
    if (!confirmed) {
      return;
    }

    try {
      setSettingsBusy(true);
      setSettingsMessage(null);
      await apiClient.deleteIdentity();
      resetAuth();
      await resetEnrollment();
      await refreshDiagnostics();
      setSettingsMessage('Identity reset completed. Re-enroll before next login.');
    } catch (error) {
      setSettingsMessage(toUserFacingError(error));
    } finally {
      setSettingsBusy(false);
    }
  };

  const generateSupportBundle = async () => {
    try {
      setSettingsBusy(true);
      setSupportMessage(null);
      const result = await apiClient.generateSupportBundle('24h');
      setSupportMessage(
        result.createdAt
          ? `Support bundle downloaded (${result.filename}) at ${result.createdAt}.`
          : `Support bundle downloaded (${result.filename}).`
      );
    } catch (error) {
      setSupportMessage(toUserFacingError(error));
    } finally {
      setSettingsBusy(false);
    }
  };

  const verifyProgress = useMemo(() => extractProgressParts(session?.progress), [session?.progress]);
  const enrollProgress = useMemo(() => {
    if (!enrollSession || enrollSession.target_frames <= 0) {
      return 0;
    }
    return enrollmentPercent(enrollSession.accepted_frames, enrollSession.target_frames);
  }, [enrollSession]);

  const authQualityMessage = useMemo(
    () => qualityFeedback(session?.quality_reason_codes),
    [session?.quality_reason_codes]
  );

  const enrollQualityMessage = useMemo(
    () => qualityFeedback(enrollSession?.reason_codes),
    [enrollSession?.reason_codes]
  );

  const renderProgressBar = (value: number | null) => {
    if (value === null) {
      return null;
    }
    return (
      <div className="progress-bar-wrap" aria-hidden="true">
        <div className="progress-bar-fill" style={{ width: `${value.toFixed(0)}%` }} />
      </div>
    );
  };

  const adminSupportUrl = (import.meta.env.VITE_ADMIN_UI_URL as string | undefined)?.trim() || 'http://127.0.0.1:3000/support';
  const telemetryDegraded =
    Boolean(diagnosticsError) ||
    (telemetryEnabled && diagnostics?.telemetry_flags?.cloud_ingest_configured === false);

  const renderCameraIssue = () => {
    if (!cameraIssue) {
      return null;
    }
    return (
      <div className="camera-issue">
        <p className="error-text">{cameraIssue}</p>
        <button className="btn-secondary" onClick={() => initializeCamera().catch(() => undefined)}>
          Retry Camera Access
        </button>
      </div>
    );
  };

  const renderLoginContent = () => {
    switch (authState) {
      case 'idle':
        return (
          <section className="phase-card">
            <h2>Login</h2>
            <p>Start liveness verification and matching against the local enrolled template.</p>
            {renderCameraIssue()}
            <button className="btn-primary" onClick={startAuth} disabled={!edgeReady || Boolean(cameraIssue)}>
              Start Login Check
            </button>
          </section>
        );
      case 'starting':
        return (
          <section className="phase-card muted">
            <p>Creating secure verification session...</p>
            {canRetryAuth(authState) && (
              <button className="btn-secondary" onClick={resetAuth}>
                Cancel
              </button>
            )}
          </section>
        );
      case 'in_challenge':
      case 'step_up':
        return (
          <section className="phase-card highlight">
            <h2>{authState === 'step_up' ? 'Additional Check' : 'Liveness Challenge'}</h2>
            <p className="instruction">{getInstructionForChallenge(session?.current_challenge)}</p>
            <p className="progress-label">
              {verifyProgress
                ? `Challenge progress: ${verifyProgress.done}/${verifyProgress.total}`
                : `Challenge progress: ${session?.progress ?? 'pending'}`}
            </p>
            {renderProgressBar(verifyProgress?.percent ?? null)}
            <p className="frame-count">Frames analyzed: {frameCount}</p>
            <p className="quality-feedback">{authQualityMessage}</p>
            {renderCameraIssue()}
            {demoMode && typeof session?.risk_score === 'number' && (
              <p className="demo-note">
                Demo metrics: risk {session.risk_score.toFixed(3)}
                {typeof session.similarity_score === 'number'
                  ? ` | similarity ${session.similarity_score.toFixed(3)}`
                  : ''}
              </p>
            )}
            <div className="button-group">
              <button className="btn-primary" onClick={finishAuth}>
                {authState === 'step_up' ? 'Complete Additional Check' : 'Finish Login'}
              </button>
              <button className="btn-secondary" onClick={resetAuth}>
                Cancel
              </button>
            </div>
          </section>
        );
      case 'step_up_notice':
        return (
          <section className="phase-card notice">
            <h2>Additional check required</h2>
            <p>The risk policy requested one more challenge sequence. Continuing automatically.</p>
            <p>
              Additional challenges: <strong>{session?.step_up_challenges?.length ?? 0}</strong>
            </p>
            <div className="button-group">
              <button className="btn-primary" onClick={continueStepUp}>
                Continue now
              </button>
              <button className="btn-secondary" onClick={resetAuth}>
                Cancel
              </button>
            </div>
          </section>
        );
      case 'finishing':
        return (
          <section className="phase-card muted">
            <p>Finalizing decision...</p>
            {canRetryAuth(authState) && (
              <button className="btn-secondary" onClick={resetAuth}>
                Cancel
              </button>
            )}
          </section>
        );
      case 'success':
      case 'error':
        return (
          <section className={`phase-card ${authState === 'success' ? 'success' : 'error'}`}>
            <h2>{authState === 'success' ? 'Login Successful' : 'Login Failed'}</h2>
            <p>{summarizeDecision(session?.decision)}</p>
            {session?.liveness_passed !== undefined && (
              <p>Liveness: {session.liveness_passed ? 'Passed' : 'Failed'}</p>
            )}
            {typeof session?.similarity_score === 'number' && (
              <p>Similarity: {session.similarity_score.toFixed(3)}</p>
            )}
            {typeof session?.risk_score === 'number' && <p>Risk score: {session.risk_score.toFixed(3)}</p>}
            {authError && <p className="error-text">{authError}</p>}
            {authHint && <p className="hint-text">{authHint}</p>}
            {authReasonMessages.length > 0 && <p>Reasons: {authReasonMessages.join(' | ')}</p>}
            {canRetryAuth(authState) && (
              <button className="btn-primary" onClick={resetAuth}>
                Retry Login
              </button>
            )}
          </section>
        );
      default:
        return null;
    }
  };

  const renderEnrollContent = () => {
    switch (enrollState) {
      case 'idle':
        return (
          <section className="phase-card">
            <h2>Enroll Face</h2>
            <p>Capture high-quality frames. Raw camera frames are never stored.</p>
            {renderCameraIssue()}
            <div className="wizard-steps">
              <span className="active">1. Start</span>
              <span>2. Capture</span>
              <span>3. Commit</span>
            </div>
            <label className="field-row">
              <span>Template label</span>
              <input value={enrollLabel} onChange={(event) => setEnrollLabel(event.target.value)} />
            </label>
            <button className="btn-primary" onClick={startEnrollment} disabled={!edgeReady || Boolean(cameraIssue)}>
              Start Enrollment
            </button>
          </section>
        );
      case 'starting':
        return (
          <section className="phase-card muted">
            <p>Creating enrollment session...</p>
            {canRetryEnroll(enrollState) && (
              <button className="btn-secondary" onClick={() => resetEnrollment()}>
                Cancel
              </button>
            )}
          </section>
        );
      case 'capturing':
        return (
          <section className="phase-card highlight">
            <h2>Capture Good Frames</h2>
            <div className="wizard-steps">
              <span>1. Start</span>
              <span className="active">2. Capture</span>
              <span>3. Commit</span>
            </div>
            <p>
              Good frames: {enrollSession?.accepted_frames ?? 0}/{enrollSession?.target_frames ?? 0}
            </p>
            {renderProgressBar(enrollProgress)}
            <p className="quality-feedback">{enrollQualityMessage}</p>
            {renderCameraIssue()}
            <div className="button-group">
              <button className="btn-secondary" onClick={captureEnrollFrame} disabled={Boolean(cameraIssue)}>
                Capture Frame
              </button>
              <button
                className="btn-primary"
                onClick={commitEnrollment}
                disabled={(enrollSession?.accepted_frames ?? 0) < (enrollSession?.target_frames ?? 0)}
              >
                Commit Template
              </button>
              <button className="btn-secondary" onClick={() => resetEnrollment()}>
                Reset
              </button>
            </div>
          </section>
        );
      case 'committing':
        return (
          <section className="phase-card muted">
            <p>Creating encrypted template...</p>
            {canRetryEnroll(enrollState) && (
              <button className="btn-secondary" onClick={() => resetEnrollment()}>
                Cancel
              </button>
            )}
          </section>
        );
      case 'success':
        return (
          <section className="phase-card success">
            <h2>Enrollment Complete</h2>
            <div className="wizard-steps">
              <span>1. Start</span>
              <span>2. Capture</span>
              <span className="active">3. Commit</span>
            </div>
            <p>Template ID: {enrollSession?.template_id}</p>
            <p>
              Frames accepted: {enrollSession?.accepted_frames}/{enrollSession?.target_frames}
            </p>
            <p>Next step: switch to Login tab and run a verification session.</p>
            <button className="btn-primary" onClick={() => resetEnrollment()}>
              Enroll Again
            </button>
          </section>
        );
      case 'error':
        return (
          <section className="phase-card error">
            <h2>Enrollment Error</h2>
            {enrollError && <p className="error-text">{enrollError}</p>}
            {enrollHint && <p className="hint-text">{enrollHint}</p>}
            {enrollReasonMessages.length > 0 && <p>Reasons: {enrollReasonMessages.join(' | ')}</p>}
            <div className="button-group">
              <button className="btn-secondary" onClick={() => setEnrollState('capturing')} disabled={!canRetryEnroll(enrollState)}>
                Retry Capture
              </button>
              <button className="btn-primary" onClick={() => resetEnrollment()} disabled={!canRetryEnroll(enrollState)}>
                Reset Session
              </button>
            </div>
          </section>
        );
      default:
        return null;
    }
  };

  const renderSettingsContent = () => {
    return (
      <section className="phase-card settings-card">
        <h2>Settings</h2>

        <div className="settings-row">
          <label>
            <input
              type="checkbox"
              checked={demoMode}
              onChange={(event) => onDemoModeChange(event.target.checked)}
            />
            Demo Mode
          </label>
          <span className="settings-note">Shows extra decision detail locally only.</span>
        </div>

        <div className="settings-row">
          <label>
            <input
              type="checkbox"
              checked={telemetryEnabled}
              disabled={!telemetryRuntimeAvailable || settingsBusy || !edgeReady}
              onChange={(event) => updateTelemetryEnabled(event.target.checked)}
            />
            Telemetry Enabled
          </label>
          {!telemetryRuntimeAvailable && <span className="settings-note">Runtime unavailable</span>}
        </div>

        <div className="settings-grid">
          <div>
            <strong>Status</strong>
            <p>{telemetryEnabled ? 'Enabled' : 'Disabled'}</p>
          </div>
          <div>
            <strong>Cloud telemetry</strong>
            <p>{telemetryDegraded ? 'Degraded (local auth still functional)' : 'Healthy'}</p>
          </div>
          <div>
            <strong>Last error</strong>
            <p>{diagnostics?.last_error_summary ?? diagnostics?.telemetry?.last_export_error ?? 'none'}</p>
          </div>
          <div>
            <strong>Outbox</strong>
            <p>{diagnostics?.outbox_pending_count ?? diagnostics?.telemetry?.outbox?.pending_count ?? 0}</p>
          </div>
          <div>
            <strong>DLQ</strong>
            <p>{diagnostics?.dlq_count ?? diagnostics?.telemetry?.outbox?.dlq_count ?? 0}</p>
          </div>
          <div>
            <strong>Device fingerprint</strong>
            <p>
              <code>{diagnostics?.device_key_fingerprint ?? 'n/a'}</code>
            </p>
          </div>
        </div>

        <div className="button-group left">
          <button className="btn-secondary" disabled={settingsBusy || !edgeReady} onClick={resetIdentity}>
            Reset Identity
          </button>
          <button className="btn-secondary" disabled={settingsBusy} onClick={() => refreshDiagnostics()}>
            Refresh Diagnostics
          </button>
          <button className="btn-primary" disabled={settingsBusy} onClick={generateSupportBundle}>
            Generate Support Bundle
          </button>
          <a className="inline-link" href={adminSupportUrl} target="_blank" rel="noreferrer">
            Open Admin Support
          </a>
        </div>

        {settingsMessage && <p className="settings-note">{settingsMessage}</p>}
        {supportMessage && <p className="settings-note">{supportMessage}</p>}
        {diagnosticsError && <p className="settings-note">{diagnosticsError}</p>}
      </section>
    );
  };

  return (
    <div className="camera-view">
      {(activeTab === 'login' || activeTab === 'enroll') && (
        <section className="camera-panel">
          <video ref={videoRef} autoPlay playsInline width="640" height="480" className="camera-feed" />
          {edgeError && !edgeReady && <p className="edge-warning">Edge unavailable: {edgeError}</p>}
        </section>
      )}

      <section className="flow-panel">
        {activeTab === 'login' && renderLoginContent()}
        {activeTab === 'enroll' && renderEnrollContent()}
        {activeTab === 'settings' && renderSettingsContent()}
      </section>
    </div>
  );
};

export default CameraView;
