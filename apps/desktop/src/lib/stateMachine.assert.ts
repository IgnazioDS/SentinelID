import { AUTH_RETRY_ALLOWED, ENROLL_RETRY_ALLOWED, AuthState, EnrollState } from './stateMachine';

const AUTH_STATES: AuthState[] = [
  'idle',
  'starting',
  'in_challenge',
  'step_up_notice',
  'step_up',
  'finishing',
  'success',
  'error',
];

const ENROLL_STATES: EnrollState[] = [
  'idle',
  'starting',
  'capturing',
  'committing',
  'success',
  'error',
];

// Compile-time and runtime assertion: every state must preserve a retry/reset path.
for (const state of AUTH_STATES) {
  if (!AUTH_RETRY_ALLOWED[state]) {
    throw new Error(`Auth state ${state} has no retry/reset path`);
  }
}

for (const state of ENROLL_STATES) {
  if (!ENROLL_RETRY_ALLOWED[state]) {
    throw new Error(`Enroll state ${state} has no retry/reset path`);
  }
}
