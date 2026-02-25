import { NextRequest } from 'next/server';

const CLOUD_BASE_URL = process.env.NEXT_PUBLIC_CLOUD_BASE_URL?.trim();
const ADMIN_TOKEN = process.env.NEXT_PUBLIC_ADMIN_TOKEN?.trim();

function configErrorResponse() {
  return Response.json(
    {
      detail:
        'Admin configuration missing NEXT_PUBLIC_CLOUD_BASE_URL. Set it in environment and restart the admin container.',
    },
    { status: 500 }
  );
}

function buildUpstreamUrl(path: string[], request: NextRequest): string {
  const base = (CLOUD_BASE_URL || '').replace(/\/+$/, '');
  const suffix = path.join('/');
  const query = request.nextUrl.search;
  return `${base}/${suffix}${query}`;
}

async function proxyRequest(request: NextRequest, context: { params: { path: string[] } }) {
  if (!CLOUD_BASE_URL) {
    return configErrorResponse();
  }

  const path = context.params.path || [];
  const upstreamUrl = buildUpstreamUrl(path, request);

  const headers = new Headers(request.headers);
  headers.delete('host');
  if (ADMIN_TOKEN && !headers.has('X-Admin-Token')) {
    headers.set('X-Admin-Token', ADMIN_TOKEN);
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
