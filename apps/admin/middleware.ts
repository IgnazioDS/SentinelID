import { NextRequest, NextResponse } from 'next/server';

const SESSION_COOKIE = 'sentinelid_admin_session';

function decodeBase64Url(input: string): string | null {
  try {
    const base64 = input.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
    return atob(padded);
  } catch {
    return null;
  }
}

function toBase64Url(bytes: Uint8Array): string {
  let binary = '';
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

async function hmacSha256(payload: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload));
  return toBase64Url(new Uint8Array(signature));
}

async function hasValidSession(request: NextRequest): Promise<boolean> {
  const secret = process.env.ADMIN_UI_SESSION_SECRET?.trim();
  if (!secret) {
    return false;
  }
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    return false;
  }
  const [payloadB64, signature] = token.split('.');
  if (!payloadB64 || !signature) {
    return false;
  }

  const expected = await hmacSha256(payloadB64, secret);
  if (expected !== signature) {
    return false;
  }

  const raw = decodeBase64Url(payloadB64);
  if (!raw) {
    return false;
  }

  try {
    const parsed = JSON.parse(raw) as { exp?: number };
    return typeof parsed.exp === 'number' && parsed.exp > Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  if (await hasValidSession(request)) {
    return NextResponse.next();
  }

  const { pathname, search } = request.nextUrl;
  if (pathname.startsWith('/api/cloud/')) {
    return NextResponse.json({ detail: 'Unauthorized' }, { status: 401 });
  }

  const loginUrl = new URL('/login', request.url);
  const next = `${pathname}${search}`;
  if (next !== '/login') {
    loginUrl.searchParams.set('next', next);
  }
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: [
    '/',
    '/events/:path*',
    '/devices/:path*',
    '/support/:path*',
    '/stats/:path*',
    '/api/cloud/:path*',
  ],
};
