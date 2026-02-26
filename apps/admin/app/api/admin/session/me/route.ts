import { NextRequest, NextResponse } from 'next/server';
import { getAdminServerConfig } from '../../../../../lib/server-env';
import { readSessionFromRequest } from '../../../../../lib/session';

export const runtime = 'nodejs';

export async function GET(request: NextRequest) {
  let config;
  try {
    config = getAdminServerConfig();
  } catch (error) {
    return NextResponse.json(
      { detail: error instanceof Error ? error.message : 'Admin configuration is invalid' },
      { status: 500 },
    );
  }

  const session = readSessionFromRequest(request, config.adminUiSessionSecret);
  if (!session) {
    return NextResponse.json({ detail: 'Unauthorized' }, { status: 401 });
  }
  return NextResponse.json({
    username: session.sub,
    expires_at: new Date(session.exp * 1000).toISOString(),
  });
}
