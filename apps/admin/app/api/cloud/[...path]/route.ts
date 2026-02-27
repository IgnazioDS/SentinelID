import { NextRequest } from 'next/server';
import { getAdminServerConfig } from '../../../../lib/server-env';
import { readSessionFromRequest } from '../../../../lib/session';

export const runtime = 'nodejs';

function configErrorResponse() {
  return Response.json(
    {
      detail:
        'Admin configuration missing CLOUD_BASE_URL (or NEXT_PUBLIC_CLOUD_BASE_URL fallback). Set it and restart admin.',
    },
    { status: 500 }
  );
}

function buildUpstreamUrl(baseUrl: string, path: string[], request: NextRequest): string {
  const base = (baseUrl || '').replace(/\/+$/, '');
  const suffix = path.join('/');
  const query = request.nextUrl.search;
  return `${base}/${suffix}${query}`;
}

async function proxyRequest(request: NextRequest, context: { params: { path: string[] } }) {
  let config;
  try {
    config = getAdminServerConfig();
  } catch {
    return configErrorResponse();
  }

  const session = readSessionFromRequest(request, config.adminUiSessionSecret);
  if (!session) {
    return Response.json({ detail: 'Unauthorized' }, { status: 401 });
  }

  const path = context.params.path || [];
  const upstreamUrl = buildUpstreamUrl(config.cloudBaseUrl, path, request);

  const headers = new Headers(request.headers);
  headers.delete('host');
  headers.delete('x-admin-token');
  if (config.adminApiToken) {
    headers.set('X-Admin-Token', config.adminApiToken);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    body: request.method === 'GET' || request.method === 'HEAD' ? undefined : await request.arrayBuffer(),
    cache: 'no-store',
  };

  const upstream = await fetch(upstreamUrl, init);

  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete('content-encoding');
  responseHeaders.delete('transfer-encoding');

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export async function GET(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}

export async function POST(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}

export async function PUT(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}

export async function PATCH(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}

export async function DELETE(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}
