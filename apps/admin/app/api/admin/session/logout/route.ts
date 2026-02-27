import { NextRequest, NextResponse } from 'next/server';
import { ADMIN_SESSION_COOKIE } from '../../../../../lib/session';

export const runtime = 'nodejs';

function shouldUseSecureCookie(request: NextRequest): boolean {
  const forced = process.env.ADMIN_UI_SESSION_SECURE?.trim().toLowerCase();
  if (forced === '1' || forced === 'true' || forced === 'yes') return true;
  if (forced === '0' || forced === 'false' || forced === 'no') return false;
  const forwardedProto = request.headers.get('x-forwarded-proto');
  if (forwardedProto) {
    return forwardedProto === 'https';
  }
  return request.nextUrl.protocol === 'https:';
}

export async function POST(request: NextRequest) {
  const response = NextResponse.json({ status: 'ok' });
  response.cookies.set({
    name: ADMIN_SESSION_COOKIE,
    value: '',
    httpOnly: true,
    sameSite: 'strict',
    secure: shouldUseSecureCookie(request),
    path: '/',
    maxAge: 0,
  });
  return response;
}
