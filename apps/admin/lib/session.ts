import { createHmac, timingSafeEqual } from 'crypto';
import { NextRequest } from 'next/server';

export const ADMIN_SESSION_COOKIE = 'sentinelid_admin_session';

export interface AdminSessionPayload {
  sub: string;
  iat: number;
  exp: number;
}

function toBase64Url(input: string | Buffer): string {
  const value = Buffer.isBuffer(input) ? input : Buffer.from(input, 'utf-8');
  return value
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

function fromBase64Url(input: string): Buffer {
  const base64 = input.replace(/-/g, '+').replace(/_/g, '/');
  const padding = base64.length % 4 === 0 ? '' : '='.repeat(4 - (base64.length % 4));
  return Buffer.from(base64 + padding, 'base64');
}

function signPayload(payloadB64: string, secret: string): string {
  const digest = createHmac('sha256', secret).update(payloadB64).digest();
  return toBase64Url(digest);
}

export function createSessionToken(
  subject: string,
  ttlMinutes: number,
  secret: string,
  nowEpochSeconds: number = Math.floor(Date.now() / 1000),
): string {
  const payload: AdminSessionPayload = {
    sub: subject,
    iat: nowEpochSeconds,
    exp: nowEpochSeconds + ttlMinutes * 60,
  };
  const payloadB64 = toBase64Url(JSON.stringify(payload));
  const signature = signPayload(payloadB64, secret);
  return `${payloadB64}.${signature}`;
}

export function verifySessionToken(
  token: string | undefined,
  secret: string,
  nowEpochSeconds: number = Math.floor(Date.now() / 1000),
): AdminSessionPayload | null {
  if (!token) return null;
  const [payloadB64, signature] = token.split('.');
  if (!payloadB64 || !signature) return null;

  const expectedSignature = signPayload(payloadB64, secret);
  const left = Buffer.from(signature, 'utf-8');
  const right = Buffer.from(expectedSignature, 'utf-8');
  if (left.length !== right.length || !timingSafeEqual(left, right)) {
    return null;
  }

  let payload: AdminSessionPayload;
  try {
    payload = JSON.parse(fromBase64Url(payloadB64).toString('utf-8')) as AdminSessionPayload;
  } catch {
    return null;
  }
  if (!payload || typeof payload.sub !== 'string' || typeof payload.exp !== 'number') {
    return null;
  }
  if (payload.exp <= nowEpochSeconds) {
    return null;
  }
  return payload;
}

export function readSessionFromRequest(
  request: NextRequest,
  secret: string,
): AdminSessionPayload | null {
  return verifySessionToken(request.cookies.get(ADMIN_SESSION_COOKIE)?.value, secret);
}
