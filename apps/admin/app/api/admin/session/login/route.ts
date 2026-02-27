import bcrypt from 'bcryptjs';
import { NextRequest, NextResponse } from 'next/server';
import { getAdminServerConfig } from '../../../../../lib/server-env';
import { ADMIN_SESSION_COOKIE, createSessionToken } from '../../../../../lib/session';

export const runtime = 'nodejs';

interface LoginBody {
  username?: string;
  password?: string;
}

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
  let body: LoginBody;
  try {
    body = (await request.json()) as LoginBody;
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON request body' }, { status: 400 });
  }

  const username = (body.username || '').trim();
  const password = body.password || '';
  if (!username || !password) {
    return NextResponse.json({ detail: 'username and password are required' }, { status: 400 });
  }

  let config;
  try {
    config = getAdminServerConfig();
  } catch (error) {
    return NextResponse.json(
      { detail: error instanceof Error ? error.message : 'Admin configuration is invalid' },
      { status: 500 },
    );
  }

  if (username !== config.adminUiUsername) {
    return NextResponse.json({ detail: 'Invalid credentials' }, { status: 401 });
  }
  const isValidPassword = await bcrypt.compare(password, config.adminUiPasswordHash);
  if (!isValidPassword) {
    return NextResponse.json({ detail: 'Invalid credentials' }, { status: 401 });
  }

  const nowSeconds = Math.floor(Date.now() / 1000);
  const token = createSessionToken(
    config.adminUiUsername,
    config.adminUiSessionTtlMinutes,
    config.adminUiSessionSecret,
    nowSeconds,
  );
  const expires = new Date((nowSeconds + config.adminUiSessionTtlMinutes * 60) * 1000);

  const response = NextResponse.json({
    username: config.adminUiUsername,
    expires_at: expires.toISOString(),
  });
  response.cookies.set({
    name: ADMIN_SESSION_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: 'strict',
    secure: shouldUseSecureCookie(request),
    path: '/',
    expires,
  });
  return response;
}
