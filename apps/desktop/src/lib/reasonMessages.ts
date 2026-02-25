const REASON_MESSAGES: Record<string, string> = {
  SUCCESS: 'Verification completed successfully.',
  LIVENESS_PASSED: 'Liveness checks passed.',
  LIVENESS_FAILED: 'Liveness check failed. Follow the movement challenge and retry.',
  CHALLENGE_TIMEOUT: 'Challenge timed out. Restart and complete each step promptly.',
  BLINK_NOT_DETECTED: 'Blink was not detected. Keep your face in frame and blink naturally.',
  HEAD_TURN_NOT_DETECTED: 'Head movement was not detected. Follow turn instructions slowly.',
  NO_FACE: 'No face detected. Center your face in the camera frame.',
  NO_FACE_DETECTED: 'No face detected. Center your face in the camera frame.',
  MULTIPLE_FACES: 'Multiple faces detected. Only one person should be visible.',
  MULTIPLE_FACES_DETECTED: 'Multiple faces detected. Only one person should be visible.',
  FACE_TOO_SMALL: 'Move closer to the camera so your face is larger in frame.',
  FACE_TOO_LARGE: 'Move slightly back from the camera.',
  FACE_NOT_CENTERED: 'Center your face in the preview box.',
  LOW_QUALITY: 'Image quality is low. Improve lighting and keep still.',
  LOW_IMAGE_QUALITY: 'Image quality is low. Improve lighting and keep still.',
  TOO_BLURRY: 'Image is blurry. Hold still for a sharper frame.',
  TOO_DARK: 'Scene is too dark. Increase front lighting.',
  POOR_LIGHTING: 'Lighting is poor. Use even front lighting.',
  POSE_TOO_LARGE: 'Head angle is too large. Face the camera directly.',
  FACE_OBSCURED: 'Face appears obscured. Remove obstructions and retry.',
  NOT_ENROLLED: 'No face template is enrolled yet. Complete enrollment first.',
  ENROLL_INCOMPLETE: 'Enrollment needs more good frames before commit.',
  SIMILARITY_BELOW_THRESHOLD: 'Face match confidence is below threshold.',
  MODEL_UNAVAILABLE: 'Face model is unavailable. Retry shortly.',
  FALLBACK_EMBEDDING_USED: 'Development fallback embedding path was used.',
  RISK_STEP_UP: 'Additional verification is required.',
  STEP_UP_REQUIRED: 'Additional verification is required.',
  STEP_UP_COMPLETED: 'Additional verification completed.',
  STEP_UP_FAILED: 'Additional verification failed.',
  MAX_STEP_UPS_REACHED: 'Maximum additional-check attempts reached.',
  RISK_HIGH: 'Risk score is too high. Access denied.',
  SPOOF_SUSPECT_SCREEN: 'Potential screen replay detected.',
  SPOOF_SUSPECT_TEMPORAL: 'Abnormal motion pattern detected.',
  SPOOF_SUSPECT_BOUNDARY: 'Face boundary pattern is suspicious.',
  INVALID_SESSION: 'Session is invalid. Start a new session.',
  SESSION_EXPIRED: 'Session expired. Start a new session.',
  SESSION_ALREADY_FINISHED: 'Session already ended. Start a new session.',
  INTERNAL_ERROR: 'Internal service error. Retry shortly.',
};

export function reasonCodeToMessage(code: string): string {
  const normalized = code.trim();
  if (!normalized) {
    return 'Unknown reason.';
  }
  return REASON_MESSAGES[normalized] ?? normalized;
}

export function reasonCodesToMessages(reasonCodes: string[] | undefined | null): string[] {
  if (!reasonCodes || reasonCodes.length === 0) {
    return [];
  }
  return reasonCodes.map((reason) => reasonCodeToMessage(reason));
}

export function summarizeDecision(decision: string | undefined): string {
  const normalized = (decision ?? '').toLowerCase();
  if (normalized === 'allow') return 'Access granted';
  if (normalized === 'deny') return 'Access denied';
  if (normalized === 'step_up') return 'Additional check required';
  return 'Decision pending';
}
