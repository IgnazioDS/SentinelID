export type AuthState =
  | 'idle'
  | 'starting'
  | 'in_challenge'
  | 'step_up_notice'
  | 'step_up'
  | 'finishing'
  | 'success'
  | 'error';

export type EnrollState =
  | 'idle'
  | 'starting'
  | 'capturing'
  | 'committing'
  | 'success'
  | 'error';

export const AUTH_RETRY_ALLOWED: Record<AuthState, boolean> = {
  idle: true,
  starting: true,
  in_challenge: true,
  step_up_notice: true,
  step_up: true,
  finishing: true,
  success: true,
  error: true,
};

export const ENROLL_RETRY_ALLOWED: Record<EnrollState, boolean> = {
  idle: true,
  starting: true,
  capturing: true,
  committing: true,
  success: true,
  error: true,
};

export function canRetryAuth(state: AuthState): boolean {
  return AUTH_RETRY_ALLOWED[state];
}

export function canRetryEnroll(state: EnrollState): boolean {
  return ENROLL_RETRY_ALLOWED[state];
}

export function assertStateMachineRecoveryCoverage(): void {
  const missingAuth = Object.entries(AUTH_RETRY_ALLOWED)
    .filter(([, allowed]) => !allowed)
    .map(([state]) => state);
  const missingEnroll = Object.entries(ENROLL_RETRY_ALLOWED)
    .filter(([, allowed]) => !allowed)
    .map(([state]) => state);

  if (missingAuth.length > 0 || missingEnroll.length > 0) {
    throw new Error(
      `Retry coverage missing for auth=[${missingAuth.join(',')}], enroll=[${missingEnroll.join(',')}]`
    );
  }
}
