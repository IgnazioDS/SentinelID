const DEFAULT_SESSION_TTL_MINUTES = 480;

function stripWrappingQuotes(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith("'") && trimmed.endsWith("'")) ||
    (trimmed.startsWith('"') && trimmed.endsWith('"'))
  ) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

function requireEnv(name: string): string {
  const value = process.env[name] ? stripWrappingQuotes(process.env[name] as string) : '';
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

function resolveCloudBaseUrl(): string {
  const rawValue =
    process.env.CLOUD_BASE_URL || process.env.NEXT_PUBLIC_CLOUD_BASE_URL || '';
  const cloudBaseUrl = stripWrappingQuotes(rawValue);
  if (!cloudBaseUrl) {
    throw new Error(
      'Missing required env var: CLOUD_BASE_URL (or NEXT_PUBLIC_CLOUD_BASE_URL fallback).',
    );
  }

  let parsed: URL;
  try {
    parsed = new URL(cloudBaseUrl);
  } catch {
    throw new Error('CLOUD_BASE_URL must be an absolute URL.');
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('CLOUD_BASE_URL must use http or https.');
  }

  return parsed.toString().replace(/\/+$/, '');
}

export interface AdminServerConfig {
  cloudBaseUrl: string;
  adminApiToken: string;
  adminUiUsername: string;
  adminUiPasswordHash: string;
  adminUiSessionSecret: string;
  adminUiSessionTtlMinutes: number;
}

function resolveAdminUiPasswordHash(): string {
  const directHash = process.env.ADMIN_UI_PASSWORD_HASH
    ? stripWrappingQuotes(process.env.ADMIN_UI_PASSWORD_HASH)
    : '';
  if (directHash) {
    return directHash;
  }

  const encodedHash = process.env.ADMIN_UI_PASSWORD_HASH_B64
    ? stripWrappingQuotes(process.env.ADMIN_UI_PASSWORD_HASH_B64)
    : '';
  if (!encodedHash) {
    throw new Error(
      'Missing required env var: ADMIN_UI_PASSWORD_HASH (or ADMIN_UI_PASSWORD_HASH_B64).',
    );
  }

  let decoded = '';
  try {
    decoded = Buffer.from(encodedHash, 'base64').toString('utf8').trim();
  } catch (error) {
    throw new Error(`Invalid ADMIN_UI_PASSWORD_HASH_B64 value: ${(error as Error).message}`);
  }

  if (!decoded) {
    throw new Error('ADMIN_UI_PASSWORD_HASH_B64 decoded to an empty value.');
  }
  return decoded;
}

export function getAdminServerConfig(): AdminServerConfig {
  const ttlRaw = process.env.ADMIN_UI_SESSION_TTL_MINUTES?.trim();
  const parsedTtl = ttlRaw ? Number.parseInt(ttlRaw, 10) : DEFAULT_SESSION_TTL_MINUTES;
  const adminUiSessionTtlMinutes =
    Number.isFinite(parsedTtl) && parsedTtl > 0 ? parsedTtl : DEFAULT_SESSION_TTL_MINUTES;

  return {
    cloudBaseUrl: resolveCloudBaseUrl(),
    adminApiToken: requireEnv('ADMIN_API_TOKEN'),
    adminUiUsername: requireEnv('ADMIN_UI_USERNAME'),
    adminUiPasswordHash: resolveAdminUiPasswordHash(),
    adminUiSessionSecret: requireEnv('ADMIN_UI_SESSION_SECRET'),
    adminUiSessionTtlMinutes,
  };
}
